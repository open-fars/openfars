from __future__ import annotations

import hashlib
import re
import shlex
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence

from .config import ComputeTarget
from .workspace import Workspace


class RemoteError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteResult:
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SSHExecutor:
    """OpenSSH transport that references a local key without reading its contents."""

    _SYNC_EXCLUDES = (
        ".git/",
        ".venv/",
        "outputs/",
        "workspace/",
        "__pycache__/",
        ".pytest_cache/",
        ".ruff_cache/",
        "build/",
        "dist/",
        "*.egg-info/",
        ".env",
        ".env.*",
        "wandb_config.yml",
        "wandb_config.yaml",
        "*.pem",
        "*.key",
        "id_ed25519*",
        "id_rsa*",
        "credentials*",
    )

    def __init__(self, target: ComputeTarget, workspace: Optional[Workspace] = None):
        self.target = target
        self.workspace = workspace
        self.identity_file = target.resolved_identity_file()
        if not self.identity_file.is_file():
            raise RemoteError(f"SSH identity file does not exist: {self.identity_file}")
        if not shutil.which("ssh"):
            raise RemoteError("OpenSSH client 'ssh' is not installed")

    def probe(self, timeout: int = 30) -> RemoteResult:
        command = (
            "nvidia-smi --query-gpu=index,name,memory.total,driver_version "
            "--format=csv,noheader || true; "
            "python3 --version; uname -srmo"
        )
        return self.run(command, cwd=None, timeout=timeout)

    def run(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        timeout: int = 86400,
        check: bool = False,
    ) -> RemoteResult:
        remote_cwd = cwd or self.target.workdir
        script = (
            "set -euo pipefail\n"
            f"mkdir -p -- {shlex.quote(remote_cwd)}\n"
            f"cd -- {shlex.quote(remote_cwd)}\n"
            f"{command}\n"
        )
        if self.workspace:
            self.workspace.append_event(
                "remote.command",
                {
                    "target": self.target.name,
                    "host": self.target.host,
                    "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
                },
            )
        completed = subprocess.run(
            [*self._ssh_args(), "bash", "-s"],
            input=script,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        result = RemoteResult(completed.returncode, completed.stdout, completed.stderr)
        if check and completed.returncode != 0:
            raise RemoteError(
                f"Remote command failed on target '{self.target.name}' "
                f"with exit code {completed.returncode}: {completed.stderr.strip()}"
            )
        return result

    def push(self, local: Path, remote_relative: str = ".", timeout: int = 600) -> None:
        local = local.expanduser().resolve()
        if not local.exists():
            raise RemoteError(f"Local sync source does not exist: {local}")
        destination = _under(self.target.workdir, remote_relative)
        self.run(f"mkdir -p -- {shlex.quote(destination)}", cwd=None, timeout=30, check=True)
        if not self._remote_has_rsync():
            self._push_tar(local, destination, timeout)
            return
        self._require_rsync()
        command: List[str] = ["rsync", "-az"]
        if self._rsync_supports_protect_args():
            command.append("--protect-args")
        for pattern in self._SYNC_EXCLUDES:
            command.extend(["--exclude", pattern])
        command.extend(
            [
                "-e",
                self._rsync_ssh_command(),
                f"{local}/" if local.is_dir() else str(local),
                f"{self.target.user}@{self.target.host}:{destination}/",
            ]
        )
        completed = subprocess.run(
            command, text=True, capture_output=True, timeout=timeout, check=False
        )
        if completed.returncode != 0:
            raise RemoteError(f"rsync push failed: {completed.stderr.strip()}")

    def pull(self, remote_relative: str, local: Path, timeout: int = 600) -> None:
        source = _under(self.target.workdir, remote_relative)
        local = local.expanduser().resolve()
        local.mkdir(parents=True, exist_ok=True)
        if not self._remote_has_rsync():
            self._pull_tar(source, local, timeout)
            return
        self._require_rsync()
        command: List[str] = [
            "rsync",
            "-az",
        ]
        if self._rsync_supports_protect_args():
            command.append("--protect-args")
        command.extend(
            [
                "-e",
                self._rsync_ssh_command(),
                f"{self.target.user}@{self.target.host}:{source}/",
                f"{local}/",
            ]
        )
        completed = subprocess.run(
            command, text=True, capture_output=True, timeout=timeout, check=False
        )
        if completed.returncode != 0:
            raise RemoteError(f"rsync pull failed: {completed.stderr.strip()}")

    def public_description(self) -> Dict[str, Any]:
        """Safe to log: deliberately omits the identity path."""
        return {
            "name": self.target.name,
            "host": self.target.host,
            "user": self.target.user,
            "port": self.target.port,
            "workdir": self.target.workdir,
            "output_dir": self.target.output_dir,
            "datasets_dir": self.target.datasets_dir,
            "models_dir": self.target.models_dir,
        }

    def _ssh_args(self) -> Sequence[str]:
        strict = "yes" if self.target.strict_host_key_checking else "accept-new"
        return (
            "ssh",
            "-i",
            str(self.identity_file),
            "-p",
            str(self.target.port),
            "-o",
            "BatchMode=yes",
            "-o",
            f"StrictHostKeyChecking={strict}",
            f"{self.target.user}@{self.target.host}",
        )

    def _rsync_ssh_command(self) -> str:
        strict = "yes" if self.target.strict_host_key_checking else "accept-new"
        return " ".join(
            shlex.quote(value)
            for value in (
                "ssh",
                "-i",
                str(self.identity_file),
                "-p",
                str(self.target.port),
                "-o",
                "BatchMode=yes",
                "-o",
                f"StrictHostKeyChecking={strict}",
            )
        )

    @staticmethod
    def _require_rsync() -> None:
        if not shutil.which("rsync"):
            raise RemoteError("rsync is required for remote artifact synchronization")

    @staticmethod
    def _rsync_supports_protect_args() -> bool:
        completed = subprocess.run(
            ["rsync", "--version"], text=True, capture_output=True, check=False
        )
        first = completed.stdout.splitlines()[0] if completed.stdout else ""
        match = re.search(r"version\s+(\d+)\.(\d+)", first)
        return bool(match and int(match.group(1)) >= 3)

    def _remote_has_rsync(self) -> bool:
        return self.run("command -v rsync >/dev/null 2>&1", timeout=15).returncode == 0

    def _push_tar(self, local: Path, destination: str, timeout: int) -> None:
        self._require_tar()
        excludes: List[str] = []
        for pattern in self._SYNC_EXCLUDES:
            normalized = pattern.rstrip("/")
            excludes.extend(["--exclude", normalized])
        if local.is_dir():
            archive_command = ["tar", *excludes, "-C", str(local), "-cf", "-", "."]
        else:
            archive_command = [
                "tar",
                *excludes,
                "-C",
                str(local.parent),
                "-cf",
                "-",
                local.name,
            ]
        extract = f"tar -xf - -C {shlex.quote(destination)}"
        self._pipe(archive_command, [*self._ssh_args(), extract], timeout, "tar push")

    def _pull_tar(self, source: str, local: Path, timeout: int) -> None:
        self._require_tar()
        archive = f"tar -cf - -C {shlex.quote(source)} ."
        self._pipe(
            [*self._ssh_args(), archive],
            ["tar", "-xf", "-", "-C", str(local)],
            timeout,
            "tar pull",
        )

    @staticmethod
    def _pipe(
        producer_command: Sequence[str],
        consumer_command: Sequence[str],
        timeout: int,
        label: str,
    ) -> None:
        producer = subprocess.Popen(
            list(producer_command), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        assert producer.stdout is not None
        consumer = subprocess.Popen(
            list(consumer_command),
            stdin=producer.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        producer.stdout.close()
        try:
            _, consumer_error = consumer.communicate(timeout=timeout)
            producer_error = producer.stderr.read() if producer.stderr else b""
            producer_return = producer.wait(timeout=10)
        except subprocess.TimeoutExpired as error:
            producer.kill()
            consumer.kill()
            raise RemoteError(f"{label} timed out after {timeout}s") from error
        if producer_return != 0 or consumer.returncode != 0:
            message = (producer_error + b"\n" + consumer_error).decode("utf-8", errors="replace")
            raise RemoteError(f"{label} failed: {message.strip()}")

    @staticmethod
    def _require_tar() -> None:
        if not shutil.which("tar"):
            raise RemoteError("tar is required when the remote host has no rsync")


def _under(root: str, relative: str) -> str:
    candidate = PurePosixPath(root) / PurePosixPath(relative)
    if PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
        raise RemoteError("Remote relative path must stay under the configured workdir")
    return str(candidate)
