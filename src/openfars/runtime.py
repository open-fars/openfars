from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, MutableMapping, Optional, Sequence

from .config import OpenFARSConfig
from .context import ContextStore
from .models import ModelRouter
from .workspace import Workspace

EventHandler = Callable[[Mapping[str, Any]], Optional[Mapping[str, Any]]]


@dataclass
class StageResult:
    """Typed output contract shared by every agent plugin."""

    data: Any
    summary: str
    produced: Sequence[str] = field(default_factory=list)
    next_agent: Optional[str] = None
    evidence_refs: Sequence[str] = field(default_factory=list)
    decisions: Mapping[str, Any] = field(default_factory=dict)
    open_questions: Sequence[str] = field(default_factory=list)


class EventBus:
    """Small waterfall event bus inspired by DeepSeek Harness' Cordis runtime."""

    def __init__(self) -> None:
        self._handlers: MutableMapping[str, List[EventHandler]] = defaultdict(list)

    def on(self, event: str, handler: EventHandler) -> Callable[[], None]:
        self._handlers[event].append(handler)

        def dispose() -> None:
            if handler in self._handlers.get(event, []):
                self._handlers[event].remove(handler)

        return dispose

    def emit(self, event: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        current: Mapping[str, Any] = dict(payload)
        for handler in [*self._handlers.get("*", []), *self._handlers.get(event, [])]:
            replacement = handler(current)
            if replacement is not None:
                current = dict(replacement)
        return current


class PluginScope:
    """Owns registrations so unloading one agent cannot leak hooks into another."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._disposers: List[Callable[[], None]] = []

    def on(self, event: str, handler: EventHandler) -> None:
        self._disposers.append(self._bus.on(event, handler))

    def close(self) -> None:
        for dispose in reversed(self._disposers):
            dispose()
        self._disposers.clear()


class RuntimeContext:
    """Dependency-injected services visible to plugins, not global singletons."""

    def __init__(
        self,
        config: OpenFARSConfig,
        workspace: Workspace,
        router: ModelRouter,
        context_store: ContextStore,
        services: MutableMapping[str, Any],
    ) -> None:
        self.config = config
        self.workspace = workspace
        self.router = router
        self.context_store = context_store
        self._services = services

    def service(self, name: str) -> Any:
        if name not in self._services:
            raise KeyError(f"Runtime service '{name}' is not registered")
        return self._services[name]


class ResearchPlugin(ABC):
    """One replaceable agent/stage plugin."""

    name: str
    requires: Sequence[str] = ()

    def mount(self, context: RuntimeContext, scope: PluginScope) -> None:
        del context, scope

    @abstractmethod
    def run(self, context: RuntimeContext, payload: Mapping[str, Any]) -> StageResult:
        raise NotImplementedError


class PluginRuntime:
    """Durable plugin runtime with scoped hooks and interceptable stage lifecycle."""

    def __init__(
        self,
        config: OpenFARSConfig,
        workspace: Workspace,
        router: ModelRouter,
        *,
        services: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.config = config
        self.workspace = workspace
        self.router = router
        self.context_store = ContextStore(config, workspace)
        self.bus = EventBus()
        self.services: Dict[str, Any] = dict(services or {})
        self.context = RuntimeContext(config, workspace, router, self.context_store, self.services)
        self._plugins: Dict[str, ResearchPlugin] = {}
        self._scopes: Dict[str, PluginScope] = {}
        self._sequence = len(list(workspace.path("handoffs").glob("*.json")))

    def provide(self, name: str, service: Any, *, replace: bool = False) -> None:
        if name in self.services and not replace:
            raise ValueError(f"Runtime service '{name}' is already registered")
        self.services[name] = service

    def mount(self, plugin: ResearchPlugin) -> None:
        if plugin.name in self._plugins:
            raise ValueError(f"Agent plugin '{plugin.name}' is already mounted")
        missing = [name for name in plugin.requires if name not in self.services]
        if missing:
            raise ValueError(
                f"Agent plugin '{plugin.name}' requires missing services: {', '.join(missing)}"
            )
        scope = PluginScope(self.bus)
        plugin.mount(self.context, scope)
        self._plugins[plugin.name] = plugin
        self._scopes[plugin.name] = scope
        self.services[f"agent:{plugin.name}"] = plugin
        self.workspace.append_event("plugin.mounted", {"agent": plugin.name})

    def unmount(self, name: str) -> None:
        if name not in self._plugins:
            return
        self._scopes.pop(name).close()
        self._plugins.pop(name)
        self.services.pop(f"agent:{name}", None)
        self.workspace.append_event("plugin.unmounted", {"agent": name})

    def on(self, event: str, handler: EventHandler) -> Callable[[], None]:
        return self.bus.on(event, handler)

    def run(self, name: str, payload: Mapping[str, Any]) -> StageResult:
        try:
            plugin = self._plugins[name]
        except KeyError as error:
            raise KeyError(f"Agent plugin '{name}' is not mounted") from error
        envelope = self.bus.emit("stage.before", {"agent": name, "input": dict(payload)})
        prepared = envelope.get("input", payload)
        if not isinstance(prepared, Mapping):
            raise TypeError("stage.before must leave an input mapping")
        self.workspace.append_event("agent.lifecycle", {"agent": name, "phase": "start"})
        try:
            result = plugin.run(self.context, prepared)
        except Exception as error:
            self.workspace.append_event(
                "agent.lifecycle",
                {"agent": name, "phase": "error", "error": str(error)},
            )
            self.bus.emit("stage.error", {"agent": name, "error": str(error), "input": prepared})
            raise
        if not isinstance(result, StageResult):
            raise TypeError(f"Agent plugin '{name}' returned no StageResult")
        self._sequence += 1
        self.context_store.handoff(
            sequence=self._sequence,
            agent=name,
            stage=name,
            summary=result.summary,
            produced=result.produced,
            next_agent=result.next_agent,
            evidence_refs=result.evidence_refs,
            decisions=result.decisions,
            open_questions=result.open_questions,
        )
        self.workspace.append_event(
            "agent.lifecycle",
            {
                "agent": name,
                "phase": "complete",
                "produced": list(result.produced),
                "next_agent": result.next_agent,
            },
        )
        self.bus.emit("stage.after", {"agent": name, "result": result})
        return result

    def close(self) -> None:
        for name in list(reversed(self._plugins)):
            self.unmount(name)

    def __enter__(self) -> "PluginRuntime":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
