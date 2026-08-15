import * as THREE from "./three.legacy.module.min.js?v=0.2.0";

const ROLE_ORDER = [
  "director", "librarian", "explorer", "critic", "task_designer", "planner",
  "experimenter", "evaluator", "visualizer", "writer", "podcaster",
  "video_producer", "publisher"
];

const ROLE_COLORS = {
  director: 0xf1c76d, librarian: 0x70c8e8, explorer: 0xb38cff, critic: 0xff846f,
  task_designer: 0x78d6c6, planner: 0x76a9ff, experimenter: 0xf39a63,
  evaluator: 0xe3d96d, visualizer: 0x65d6ef, writer: 0xd69cf0,
  podcaster: 0xff9eb5, video_producer: 0x9ba7ff, publisher: 0x70e0a9
};

const STAGES = [
  ["Direction", "director"], ["Literature", "librarian"], ["Explore", "explorer"],
  ["Critique", "critic"], ["Task", "task_designer"], ["Plan", "planner"],
  ["Experiment", "experimenter"], ["Evaluate", "evaluator"],
  ["Figures", "visualizer"], ["Paper", "writer"], ["Podcast", "podcaster"],
  ["Video", "video_producer"], ["Release", "publisher"]
];

const DESKS = {
  director: [-8.8, -5.55, 0], librarian: [-4.4, -5.55, 0],
  explorer: [0, -5.55, 0], critic: [4.4, -5.55, 0],
  task_designer: [8.8, -5.55, 0],
  planner: [-10.25, -1.75, Math.PI / 2],
  experimenter: [-10.25, 2.25, Math.PI / 2],
  evaluator: [10.25, -1.75, -Math.PI / 2],
  visualizer: [10.25, 2.25, -Math.PI / 2],
  writer: [-6.75, 5.5, Math.PI], podcaster: [-2.25, 5.5, Math.PI],
  video_producer: [2.25, 5.5, Math.PI], publisher: [6.75, 5.5, Math.PI]
};

const ROOM = {width: 24, depth: 16};
const WALK_SPEED = 1.35;
const PERSONAL_SPACE = 0.82;
const HIP_HEIGHT = 1.1;
const CHAIR_SEAT_Y = 0.40;
const CHAIR_SEAT_HEIGHT = 0.12;
const CHAIR_BACK_Z = 0.45;
const CHAIR_BACK_THICKNESS = 0.11;
const TORSO_BACK_RADIUS = 0.38;
const PELVIS_BOTTOM_FROM_ROOT = HIP_HEIGHT + 0.04 - 0.14;
const SIT_ROOT_Y = CHAIR_SEAT_Y + CHAIR_SEAT_HEIGHT / 2 + 0.01 - PELVIS_BOTTOM_FROM_ROOT;
const STATUS_COLORS = {
  working: 0xffbd69, done: 0x71e2ad, ready: 0x7eafff, queued: 0x788d85,
  error: 0xff786d, stopped: 0x788d85
};
const STATUS_LABELS = {
  working: "working", done: "handoff ready", ready: "ready", queued: "queued",
  error: "needs attention", stopped: "stopped"
};
const ROOM_LINES = {
  director: "What is the strongest signal?",
  librarian: "I’ll check the evidence trail.",
  explorer: "There may be another angle.",
  critic: "What would falsify it fastest?",
  task_designer: "Can we make the rule executable?",
  planner: "Let’s test the cheapest decisive step.",
  experimenter: "I’ll preserve the run and logs.",
  evaluator: "Does the result clear the rule?",
  visualizer: "Which claim should the figure carry?",
  writer: "I’ll keep the wording inside the evidence.",
  podcaster: "What is the clearest honest story?",
  video_producer: "Which visual is actually supported?",
  publisher: "I’ll verify the release boundary."
};
const WANDER_POINTS = [
  [-5.1, -2.6], [5.1, -2.6], [-5.2, 2.5], [5.2, 2.5],
  [-7.2, 0.2], [7.2, 0.2], [-4.6, 4.0], [4.6, 4.0]
];
const MEETING_POINTS = [[-4.7, 0], [4.7, 0], [0, -3.0], [0, 3.2]];

const clamp = THREE.MathUtils.clamp;
const damp = THREE.MathUtils.damp;
const geometryCache = {
  boxes: new Map(),
  cylinders: new Map(),
  spheres: new Map(),
  dollCap: new THREE.SphereGeometry(0.295, 10, 5, 0, Math.PI * 2, 0, Math.PI / 2),
  dollNose: new THREE.ConeGeometry(0.035, 0.10, 6),
  screenContent: null
};

function screenContentGeometry() {
  if (geometryCache.screenContent) return geometryCache.screenContent;
  const positions = [];
  const indices = [];
  [[0.47, 0.11], [0.34, 0.005], [0.53, -0.10]].forEach(([width, y], index) => {
    const left = -0.07 - width / 2;
    const right = -0.07 + width / 2;
    const bottom = y - 0.0175;
    const top = y + 0.0175;
    const offset = index * 4;
    positions.push(left, bottom, 0, right, bottom, 0, right, top, 0, left, top, 0);
    indices.push(offset, offset + 1, offset + 2, offset, offset + 2, offset + 3);
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeBoundingSphere();
  geometryCache.screenContent = geometry;
  return geometry;
}

function cssColor(value, fallback) {
  try {
    return new THREE.Color(value || fallback);
  } catch (_) {
    return new THREE.Color(fallback);
  }
}

function statusColor(status) {
  return STATUS_COLORS[status] || STATUS_COLORS.queued;
}

function box(width, height, depth, material) {
  const key = [width, height, depth].join(":");
  if (!geometryCache.boxes.has(key)) {
    geometryCache.boxes.set(key, new THREE.BoxGeometry(width, height, depth));
  }
  return new THREE.Mesh(geometryCache.boxes.get(key), material);
}

function cylinder(top, bottom, height, segments, material) {
  const key = [top, bottom, height, segments].join(":");
  if (!geometryCache.cylinders.has(key)) {
    geometryCache.cylinders.set(
      key,
      new THREE.CylinderGeometry(top, bottom, height, segments)
    );
  }
  return new THREE.Mesh(geometryCache.cylinders.get(key), material);
}

function sphere(radius, widthSegments, heightSegments, material) {
  const key = [radius, widthSegments, heightSegments].join(":");
  if (!geometryCache.spheres.has(key)) {
    geometryCache.spheres.set(
      key,
      new THREE.SphereGeometry(radius, widthSegments, heightSegments)
    );
  }
  return new THREE.Mesh(geometryCache.spheres.get(key), material);
}

function addMesh(parent, mesh, position, rotation) {
  mesh.position.set(position[0], position[1], position[2]);
  if (rotation) mesh.rotation.set(rotation[0], rotation[1], rotation[2]);
  parent.add(mesh);
  return mesh;
}

function tagClickable(root, agent, kind) {
  root.traverse(function (object) {
    if (object.isMesh) object.userData = {agent: agent, kind: kind};
  });
}

class Office3D {
  constructor(container) {
    this.container = container;
    this.agents = new Map();
    this.desks = new Map();
    this.taskBlocks = new Map();
    this.projectId = null;
    this.lastHandoff = null;
    this.conversation = null;
    this.motionPaused = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.lastFrame = 0;
    this.lastBehavior = 0;
    this.nextBehavior = 4.2;
    this.needsRender = true;
    this.drag = null;
    this.pointerMoved = false;
    this.cameraYaw = 0.70;
    this.cameraPitch = 0.58;
    this.cameraRadius = 27;
    this.cameraTarget = new THREE.Vector3(0, 0.8, 0);
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.clickables = [];
    this.theme = {};
    this.isVisible = true;
    this.contextLost = false;

    this.rendererErrors = [];
    const rendererAttempts = [
      {
        label: "WebGL auto · low power",
        create: () => new THREE.WebGLRenderer({
          antialias: true, alpha: false, powerPreference: "low-power"
        })
      },
      {
        label: "WebGL auto · compatibility",
        create: () => new THREE.WebGLRenderer({
          antialias: false, alpha: false, powerPreference: "default"
        })
      }
    ];
    if (THREE.WebGL1Renderer) {
      rendererAttempts.push({
        label: "WebGL 1 compatibility",
        create: () => new THREE.WebGL1Renderer({
          antialias: false, alpha: false, powerPreference: "default"
        })
      });
    }
    for (const attempt of rendererAttempts) {
      try {
        this.renderer = attempt.create();
        this.rendererProfile = attempt.label;
        break;
      } catch (error) {
        this.rendererErrors.push(attempt.label + ": " + String(error.message || error));
      }
    }
    if (!this.renderer) {
      this.showFallback(new Error(this.rendererErrors.join(" | ")));
      return;
    }

    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.domElement.className = "room-canvas";
    this.renderer.domElement.setAttribute(
      "aria-label",
      "Interactive 3D office. Drag or use arrow keys to orbit, scroll or use plus and minus to zoom, and select a person or desk for progress."
    );
    this.renderer.domElement.addEventListener("webglcontextlost", (event) => {
      event.preventDefault();
      this.contextLost = true;
      this.setActivity("The graphics context paused. Research execution is unaffected.");
    });
    this.renderer.domElement.addEventListener("webglcontextrestored", () => {
      this.contextLost = false;
      this.needsRender = true;
      this.setActivity("The 3D office is ready again.");
    });
    this.container.replaceChildren(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.Fog(0x08110f, 24, 42);
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 80);
    this.createMaterials();
    this.createLights();
    this.createRoom();
    this.createTaskRail();
    this.createOverlay();
    this.bindControls();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.container);
    if ("IntersectionObserver" in window) {
      this.visibilityObserver = new IntersectionObserver((entries) => {
        this.isVisible = Boolean(entries[0] && entries[0].isIntersecting);
        if (this.isVisible) this.needsRender = true;
      }, {rootMargin: "120px"});
      this.visibilityObserver.observe(this.container);
    }
    this.resize();
    this.updateCamera();
    this.updateMotionButton();
    this.renderer.setAnimationLoop((time) => this.animate(time));
  }

  createMaterials() {
    this.materials = {
      floor: new THREE.MeshLambertMaterial({color: 0x14241f}),
      wall: new THREE.MeshLambertMaterial({color: 0x24443b}),
      wallSide: new THREE.MeshLambertMaterial({color: 0x1c382f}),
      trim: new THREE.MeshLambertMaterial({color: 0x10211c}),
      wood: new THREE.MeshLambertMaterial({color: 0x8f694d}),
      woodDark: new THREE.MeshLambertMaterial({color: 0x4c382d}),
      dark: new THREE.MeshLambertMaterial({color: 0x26332f}),
      screen: new THREE.MeshLambertMaterial({color: 0x13221e, emissive: 0x07110e}),
      metal: new THREE.MeshLambertMaterial({color: 0x586661}),
      glass: new THREE.MeshLambertMaterial({
        color: 0x78b5c7, transparent: true, opacity: 0.55
      }),
      whiteboard: new THREE.MeshLambertMaterial({color: 0xdfe9e4}),
      green: new THREE.MeshLambertMaterial({color: 0x3e8b64}),
      pot: new THREE.MeshLambertMaterial({color: 0xa36948}),
      skin: new THREE.MeshLambertMaterial({color: 0xc99170}),
      hair: new THREE.MeshLambertMaterial({color: 0x302b29}),
      shoe: new THREE.MeshLambertMaterial({color: 0x202927}),
      ledGreen: new THREE.MeshBasicMaterial({color: 0x71e2ad}),
      ledBlue: new THREE.MeshBasicMaterial({color: 0x70c8e8})
    };
  }

  createLights() {
    this.hemi = new THREE.HemisphereLight(0xd9f5ec, 0x17201d, 2.25);
    this.scene.add(this.hemi);
    this.keyLight = new THREE.DirectionalLight(0xfff1d3, 2.1);
    this.keyLight.position.set(5, 13, 8);
    this.scene.add(this.keyLight);
    const fill = new THREE.DirectionalLight(0x9acbff, 0.75);
    fill.position.set(-10, 7, -5);
    this.scene.add(fill);
  }

  createRoom() {
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(ROOM.width, ROOM.depth, 12, 8),
      this.materials.floor
    );
    floor.rotation.x = -Math.PI / 2;
    this.scene.add(floor);

    const grid = new THREE.GridHelper(ROOM.width, 24, 0x31534a, 0x203d35);
    grid.position.y = 0.012;
    grid.scale.z = ROOM.depth / ROOM.width;
    grid.material.transparent = true;
    grid.material.opacity = 0.34;
    this.scene.add(grid);

    const back = box(ROOM.width, 7.2, 0.2, this.materials.wall);
    back.position.set(0, 3.6, -ROOM.depth / 2);
    this.scene.add(back);
    const left = box(0.2, 7.2, ROOM.depth, this.materials.wallSide);
    left.position.set(-ROOM.width / 2, 3.6, 0);
    this.scene.add(left);
    const backTrim = box(ROOM.width, 0.18, 0.34, this.materials.trim);
    backTrim.position.set(0, 0.12, -7.85);
    this.scene.add(backTrim);

    [-7.2, 7.2].forEach((x) => {
      const frame = box(4.3, 2.25, 0.18, this.materials.trim);
      frame.position.set(x, 3.65, -7.84);
      this.scene.add(frame);
      const pane = box(3.95, 1.92, 0.10, this.materials.glass);
      pane.position.set(x, 3.65, -7.72);
      this.scene.add(pane);
      const bar = box(0.08, 1.92, 0.12, this.materials.trim);
      bar.position.set(x, 3.65, -7.63);
      this.scene.add(bar);
    });

    const board = box(4.5, 1.65, 0.16, this.materials.whiteboard);
    board.position.set(0, 3.55, -7.72);
    this.scene.add(board);
    [-1.25, -0.35, 0.55].forEach((x, index) => {
      const colors = [0x4f9e79, 0xd57668, 0x608ed8];
      const line = box(0.65 + index * 0.22, 0.055, 0.025, new THREE.MeshBasicMaterial({color: colors[index]}));
      line.position.set(x, 3.75 - index * 0.28, -7.61);
      line.rotation.z = index % 2 ? -0.12 : 0.12;
      this.scene.add(line);
    });

    this.createMeetingTable();
    this.createCoffeeBar();
    this.createServerRack();
    this.createPlant(-11.2, -6.8);
    this.createPlant(11.1, 6.7);
  }

  createMeetingTable() {
    const top = cylinder(2.15, 2.15, 0.16, 24, this.materials.wood);
    top.position.set(0, 0.73, 0);
    this.scene.add(top);
    const stem = cylinder(0.36, 0.55, 0.66, 12, this.materials.woodDark);
    stem.position.set(0, 0.34, 0);
    this.scene.add(stem);
    [[-2.65, 0], [2.65, 0], [0, -2.25], [0, 2.25]].forEach((point) => {
      const chair = this.createChair();
      chair.position.set(point[0], 0, point[1]);
      chair.rotation.y = Math.atan2(-point[0], -point[1]);
      this.scene.add(chair);
    });
    const tablet = box(0.65, 0.06, 0.45, this.materials.screen);
    tablet.position.set(0, 0.85, 0);
    tablet.rotation.y = 0.25;
    this.scene.add(tablet);
  }

  createCoffeeBar() {
    const counter = box(2.8, 0.83, 0.72, this.materials.wood);
    counter.position.set(-8.2, 0.42, 7.15);
    this.scene.add(counter);
    const machine = box(0.62, 0.72, 0.55, this.materials.dark);
    machine.position.set(-8.65, 1.17, 7.12);
    this.scene.add(machine);
    const cup = cylinder(0.12, 0.1, 0.25, 10, this.materials.whiteboard);
    cup.position.set(-7.65, 0.98, 7.1);
    this.scene.add(cup);
  }

  createServerRack() {
    const rack = box(1.05, 2.25, 0.82, this.materials.dark);
    rack.position.set(11.25, 1.13, -6.85);
    this.scene.add(rack);
    for (let row = 0; row < 6; row += 1) {
      const bay = box(0.82, 0.21, 0.04, this.materials.metal);
      bay.position.set(11.25, 0.35 + row * 0.31, -6.41);
      this.scene.add(bay);
      const led = sphere(
        0.035, 6, 4, row % 2 ? this.materials.ledGreen : this.materials.ledBlue
      );
      led.position.set(10.94, 0.35 + row * 0.31, -6.37);
      this.scene.add(led);
    }
  }

  createPlant(x, z) {
    const pot = cylinder(0.28, 0.38, 0.52, 10, this.materials.pot);
    pot.position.set(x, 0.26, z);
    this.scene.add(pot);
    for (let index = 0; index < 5; index += 1) {
      const leaf = sphere(0.34, 7, 5, this.materials.green);
      const angle = index * Math.PI * 0.4;
      leaf.scale.set(0.56, 1.35, 0.42);
      leaf.rotation.z = Math.cos(angle) * 0.45;
      leaf.rotation.x = Math.sin(angle) * 0.3;
      leaf.position.set(x + Math.cos(angle) * 0.24, 0.82 + (index % 2) * 0.22, z + Math.sin(angle) * 0.24);
      this.scene.add(leaf);
    }
  }

  createTaskRail() {
    const rail = box(22.2, 0.11, 0.14, this.materials.trim);
    rail.position.set(0, 5.72, -7.65);
    this.scene.add(rail);
    STAGES.forEach((entry, index) => {
      const x = -10.2 + index * 1.7;
      const material = new THREE.MeshLambertMaterial({
        color: 0x3a5049,
        emissive: 0x07110e
      });
      const block = box(1.34, 0.50, 0.32, material);
      block.position.set(x, 5.72, -7.47);
      block.userData = {agent: entry[1], kind: "task"};
      this.scene.add(block);
      this.clickables.push(block);
      this.taskBlocks.set(entry[1], {mesh: block, material: material});
    });
  }

  createOverlay() {
    this.overlay = document.createElement("div");
    this.overlay.className = "room-overlay";
    this.overlay.innerHTML =
      '<div class="task-hud" aria-label="Research workflow stages"><div class="task-hud-head">' +
      '<span>RESEARCH TASK GRAPH</span><small>click any stage</small></div>' +
      '<div class="task-track" role="group" aria-label="Agent stages"></div></div>' +
      '<div class="room-hint">drag to orbit · scroll to zoom · click a person</div>' +
      '<div class="room-performance">low-poly · 30 FPS cap</div>' +
      '<div class="room-activity" role="status" aria-live="polite">The office view mirrors durable research state.</div>';
    this.container.appendChild(this.overlay);
    this.taskTrack = this.overlay.querySelector(".task-track");
    this.activity = this.overlay.querySelector(".room-activity");
    this.performance = this.overlay.querySelector(".room-performance");
    STAGES.forEach((entry, index) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "task-chip queued";
      chip.dataset.agent = entry[1];
      chip.innerHTML = '<i>' + String(index + 1).padStart(2, "0") + '</i><span>' + entry[0] + "</span>";
      chip.addEventListener("click", () => this.openAgent(entry[1]));
      this.taskTrack.appendChild(chip);
    });
  }

  createChair() {
    const group = new THREE.Group();
    const seat = box(0.64, CHAIR_SEAT_HEIGHT, 0.62, this.materials.dark);
    seat.position.y = CHAIR_SEAT_Y;
    group.add(seat);
    const back = box(0.64, 0.74, CHAIR_BACK_THICKNESS, this.materials.dark);
    back.position.set(0, 0.75, CHAIR_BACK_Z);
    back.rotation.x = -0.08;
    group.add(back);
    const stem = cylinder(0.075, 0.09, 0.34, 8, this.materials.metal);
    stem.position.y = 0.21;
    group.add(stem);
    const base = cylinder(0.33, 0.33, 0.06, 8, this.materials.metal);
    base.position.y = 0.04;
    group.add(base);
    return group;
  }

  createDesk(agent, layout) {
    const group = new THREE.Group();
    group.position.set(layout[0], 0, layout[1]);
    group.rotation.y = layout[2];
    const top = box(3.15, 0.14, 1.05, this.materials.wood);
    top.position.y = 0.82;
    group.add(top);
    [-1.28, 1.28].forEach((x) => {
      [-0.36, 0.36].forEach((z) => {
        const leg = box(0.12, 0.75, 0.12, this.materials.woodDark);
        leg.position.set(x, 0.39, z);
        group.add(leg);
      });
    });
    const monitorBody = box(0.92, 0.58, 0.10, this.materials.dark);
    monitorBody.position.set(0, 1.23, -0.22);
    group.add(monitorBody);
    const roleColor = ROLE_COLORS[agent] || 0x71e2ad;
    const screenMaterial = new THREE.MeshLambertMaterial({
      color: new THREE.Color(roleColor).multiplyScalar(0.14),
      emissive: roleColor,
      emissiveIntensity: 0.45
    });
    const screen = box(0.77, 0.43, 0.025, screenMaterial);
    screen.position.set(0, 1.23, -0.158);
    group.add(screen);
    const screenLineMaterial = new THREE.MeshBasicMaterial({color: roleColor});
    const screenContent = new THREE.Mesh(screenContentGeometry(), screenLineMaterial);
    screenContent.position.set(0, 1.23, -0.137);
    group.add(screenContent);
    const stand = box(0.10, 0.30, 0.08, this.materials.dark);
    stand.position.set(0, 0.93, -0.22);
    group.add(stand);
    const keyboard = box(0.62, 0.035, 0.25, this.materials.dark);
    keyboard.position.set(0, 0.91, 0.19);
    keyboard.rotation.x = 0.04;
    group.add(keyboard);
    const mouse = sphere(0.11, 8, 5, this.materials.metal);
    mouse.scale.set(0.72, 0.38, 1.08);
    mouse.position.set(0.48, 0.925, 0.20);
    group.add(mouse);
    const statusMaterial = new THREE.MeshBasicMaterial({color: statusColor("queued")});
    const light = sphere(0.075, 8, 6, statusMaterial);
    light.position.set(1.32, 0.96, 0.16);
    group.add(light);
    const chair = this.createChair();
    chair.position.set(0, 0, 1.22);
    group.add(chair);
    tagClickable(group, agent, "desk");
    this.scene.add(group);
    this.clickables.push(...group.children.filter((item) => item.isMesh));
    return {
      group: group,
      screenMaterial: screenMaterial,
      screenLineMaterial: screenLineMaterial,
      statusMaterial: statusMaterial,
      ownedMaterials: [screenMaterial, screenLineMaterial, statusMaterial]
    };
  }

  makeLimb(parent, name, x, y, length, radius, material) {
    const joint = new THREE.Group();
    joint.name = name;
    joint.position.set(x, y, 0);
    parent.add(joint);
    const segment = cylinder(radius * 0.90, radius, length, 7, material);
    segment.position.y = -length / 2;
    joint.add(segment);
    return joint;
  }

  createDoll(agent) {
    const root = new THREE.Group();
    root.name = agent.name;
    const color = ROLE_COLORS[agent.name] || 0x71e2ad;
    const clothing = new THREE.MeshLambertMaterial({color: color});
    const clothingDark = new THREE.MeshLambertMaterial({
      color: new THREE.Color(color).multiplyScalar(0.56)
    });
    const skin = this.materials.skin;
    const hair = this.materials.hair;
    const shoe = this.materials.shoe;

    const pelvis = box(0.52, 0.28, 0.34, clothingDark);
    pelvis.position.set(0, HIP_HEIGHT + 0.04, 0);
    root.add(pelvis);
    const torso = cylinder(0.31, 0.38, 0.68, 8, clothing);
    torso.position.set(0, HIP_HEIGHT + 0.47, 0);
    root.add(torso);
    const collar = cylinder(0.12, 0.13, 0.13, 8, skin);
    collar.position.set(0, HIP_HEIGHT + 0.84, 0);
    root.add(collar);
    const head = sphere(0.29, 10, 7, skin);
    head.scale.y = 1.08;
    head.position.set(0, HIP_HEIGHT + 1.12, 0);
    root.add(head);
    const cap = new THREE.Mesh(geometryCache.dollCap, hair);
    cap.position.set(0, HIP_HEIGHT + 1.16, 0);
    root.add(cap);
    [-0.10, 0.10].forEach((x) => {
      const eye = sphere(0.026, 6, 4, shoe);
      eye.position.set(x, HIP_HEIGHT + 1.16, 0.272);
      root.add(eye);
    });
    const nose = new THREE.Mesh(geometryCache.dollNose, skin);
    nose.rotation.x = Math.PI / 2;
    nose.position.set(0, HIP_HEIGHT + 1.08, 0.31);
    root.add(nose);

    const leftHip = this.makeLimb(root, "leftHip", -0.18, HIP_HEIGHT, 0.49, 0.12, clothingDark);
    const rightHip = this.makeLimb(root, "rightHip", 0.18, HIP_HEIGHT, 0.49, 0.12, clothingDark);
    const leftKnee = this.makeLimb(leftHip, "leftKnee", 0, -0.49, 0.48, 0.105, skin);
    const rightKnee = this.makeLimb(rightHip, "rightKnee", 0, -0.49, 0.48, 0.105, skin);
    const leftAnkle = new THREE.Group();
    leftAnkle.name = "leftAnkle";
    leftAnkle.position.set(0, -0.48, 0);
    leftKnee.add(leftAnkle);
    const rightAnkle = new THREE.Group();
    rightAnkle.name = "rightAnkle";
    rightAnkle.position.set(0, -0.48, 0);
    rightKnee.add(rightAnkle);
    const leftFoot = box(0.20, 0.13, 0.38, shoe);
    leftFoot.position.set(0, -0.025, 0.12);
    leftAnkle.add(leftFoot);
    const rightFoot = box(0.20, 0.13, 0.38, shoe);
    rightFoot.position.set(0, -0.025, 0.12);
    rightAnkle.add(rightFoot);

    const leftShoulder = this.makeLimb(root, "leftShoulder", -0.38, HIP_HEIGHT + 0.66, 0.37, 0.095, clothing);
    const rightShoulder = this.makeLimb(root, "rightShoulder", 0.38, HIP_HEIGHT + 0.66, 0.37, 0.095, clothing);
    const leftElbow = this.makeLimb(leftShoulder, "leftElbow", 0, -0.37, 0.34, 0.082, skin);
    const rightElbow = this.makeLimb(rightShoulder, "rightElbow", 0, -0.37, 0.34, 0.082, skin);
    const leftHand = sphere(0.105, 7, 5, skin);
    leftHand.position.y = -0.35;
    leftElbow.add(leftHand);
    const rightHand = sphere(0.105, 7, 5, skin);
    rightHand.position.y = -0.35;
    rightElbow.add(rightHand);

    const anchor = new THREE.Object3D();
    anchor.position.set(0, HIP_HEIGHT + 1.62, 0);
    root.add(anchor);
    tagClickable(root, agent.name, "person");
    this.scene.add(root);
    root.traverse((object) => {
      if (object.isMesh) this.clickables.push(object);
    });

    const label = document.createElement("button");
    label.type = "button";
    label.className = "agent-tag queued";
    const labelDot = document.createElement("i");
    const labelText = document.createElement("span");
    labelText.textContent = agent.label || agent.name;
    label.append(labelDot, labelText);
    label.addEventListener("click", () => this.openAgent(agent.name));
    this.overlay.appendChild(label);
    const speech = document.createElement("div");
    speech.className = "agent-speech";
    this.overlay.appendChild(speech);

    return {
      name: agent.name,
      data: agent,
      root: root,
      anchor: anchor,
      label: label,
      speech: speech,
      joints: {
        leftHip: leftHip, rightHip: rightHip, leftKnee: leftKnee, rightKnee: rightKnee,
        leftAnkle: leftAnkle, rightAnkle: rightAnkle,
        leftShoulder: leftShoulder, rightShoulder: rightShoulder,
        leftElbow: leftElbow, rightElbow: rightElbow
      },
      mode: "sitting",
      route: [],
      arrivalMode: "sitting",
      arrivalYaw: 0,
      walkPhase: 0,
      blockedFor: 0,
      velocity: new THREE.Vector2(),
      actionUntil: 0,
      home: new THREE.Vector3(),
      homeYaw: 0,
      ownedMaterials: [clothing, clothingDark]
    };
  }

  setProject(payload) {
    if (!this.renderer) return;
    const agents = payload.agents || [];
    const changed = this.projectId !== payload.projectId;
    this.projectId = payload.projectId;

    if (changed) {
      this.lastHandoff = null;
      this.conversation = null;
      this.agents.forEach((actor) => {
        actor.label.remove();
        actor.speech.remove();
        this.scene.remove(actor.root);
        actor.ownedMaterials.forEach((material) => material.dispose());
      });
      this.desks.forEach((desk) => {
        this.scene.remove(desk.group);
        desk.ownedMaterials.forEach((material) => material.dispose());
      });
      this.agents.clear();
      this.desks.clear();
      this.clickables = Array.from(this.taskBlocks.values()).map((item) => item.mesh);
      agents.forEach((agent) => {
        const layout = DESKS[agent.name];
        if (!layout) return;
        const desk = this.createDesk(agent.name, layout);
        this.desks.set(agent.name, desk);
        const actor = this.createDoll(agent);
        const homeOffset = new THREE.Vector3(0, 0, 1.22).applyAxisAngle(
          new THREE.Vector3(0, 1, 0), layout[2]
        );
        actor.home.set(layout[0] + homeOffset.x, SIT_ROOT_Y, layout[1] + homeOffset.z);
        actor.homeYaw = layout[2] + Math.PI;
        actor.root.position.copy(actor.home);
        actor.root.rotation.y = actor.homeYaw;
        this.agents.set(agent.name, actor);
      });
    }

    agents.forEach((agent) => this.updateAgent(agent));
    if (this.motionPaused) {
      this.agents.forEach((actor) => this.applyPose(actor, 1, 0));
    }
    this.updateTasks();
    this.animateHandoff(payload.handoffs || []);
    this.needsRender = true;
  }

  updateAgent(agent) {
    const actor = this.agents.get(agent.name);
    if (!actor) return;
    actor.data = agent;
    actor.label.querySelector("span").textContent = agent.label || agent.name;
    actor.label.className = "agent-tag " + (agent.status || "queued");
    const desk = this.desks.get(agent.name);
    const color = statusColor(agent.status);
    if (desk) {
      desk.statusMaterial.color.setHex(color);
      const roleColor = ROLE_COLORS[agent.name] || color;
      const screenColor = agent.status === "error" ? STATUS_COLORS.error : roleColor;
      desk.screenMaterial.color.copy(new THREE.Color(screenColor).multiplyScalar(0.15));
      desk.screenMaterial.emissive.setHex(screenColor);
      desk.screenMaterial.emissiveIntensity =
        agent.status === "working" ? 0.95 : agent.status === "done" ? 0.56 : 0.36;
      desk.screenLineMaterial.color.setHex(
        agent.status === "done" ? STATUS_COLORS.done : screenColor
      );
    }
    if (agent.status === "working" && actor.mode !== "walking" && !this.isBusy(actor)) {
      this.sitAtHome(actor, "working");
    }
  }

  updateTasks() {
    const previousActiveTask = this.activeTask;
    let nextActiveTask = null;
    ROLE_ORDER.forEach((name) => {
      const actor = this.agents.get(name);
      const status = actor ? actor.data.status || "queued" : "queued";
      const item = this.taskBlocks.get(name);
      if (item) {
        const color = statusColor(status);
        item.material.color.setHex(color);
        item.material.emissive.setHex(status === "working" ? color : 0x07110e);
        item.material.emissiveIntensity = status === "working" ? 0.38 : 0.12;
        item.mesh.scale.z = status === "working" ? 1.65 : 1;
      }
      const chip = this.taskTrack.querySelector('[data-agent="' + name + '"]');
      if (chip) {
        chip.className = "task-chip " + status;
        chip.title = (actor ? actor.data.label : name) + " · " + (STATUS_LABELS[status] || status);
        chip.setAttribute("aria-label", chip.title);
        if (status === "working") {
          chip.setAttribute("aria-current", "step");
          if (previousActiveTask !== name && this.taskTrack.scrollWidth > this.taskTrack.clientWidth) {
            chip.scrollIntoView({
              behavior: this.motionPaused ? "auto" : "smooth",
              block: "nearest",
              inline: "center"
            });
          }
          nextActiveTask = name;
        } else {
          chip.removeAttribute("aria-current");
        }
      }
    });
    this.activeTask = nextActiveTask;
  }

  sitAtHome(actor, mode) {
    actor.route.length = 0;
    actor.mode = mode || (actor.data.status === "working" ? "working" : "sitting");
    actor.root.position.x = actor.home.x;
    actor.root.position.z = actor.home.z;
    actor.root.rotation.y = actor.homeYaw;
    actor.speech.classList.remove("visible");
    actor.speech.textContent = "";
  }

  buildRoute(start, target, actor) {
    if (this.lineOfSight(start, target, actor)) {
      return [new THREE.Vector3(target.x, 0, target.z)];
    }
    const step = 0.58;
    const minX = -11.25;
    const minZ = -7.25;
    const maxI = Math.round(22.5 / step);
    const maxJ = Math.round(14.5 / step);
    const toCell = (point) => ({
      i: clamp(Math.round((point.x - minX) / step), 0, maxI),
      j: clamp(Math.round((point.z - minZ) / step), 0, maxJ)
    });
    const toPoint = (cell) => new THREE.Vector3(
      minX + cell.i * step, 0, minZ + cell.j * step
    );
    const key = (i, j) => i + ":" + j;
    const startCell = toCell(start);
    const endCell = toCell(target);
    const startKey = key(startCell.i, startCell.j);
    const endKey = key(endCell.i, endCell.j);
    const open = [{...startCell, g: 0, f: 0}];
    const costs = new Map([[startKey, 0]]);
    const parents = new Map();
    const closed = new Set();
    const directions = [
      [1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1],
      [1, 1, Math.SQRT2], [1, -1, Math.SQRT2],
      [-1, 1, Math.SQRT2], [-1, -1, Math.SQRT2]
    ];

    while (open.length) {
      let bestIndex = 0;
      for (let index = 1; index < open.length; index += 1) {
        if (open[index].f < open[bestIndex].f) bestIndex = index;
      }
      const current = open.splice(bestIndex, 1)[0];
      const currentKey = key(current.i, current.j);
      if (closed.has(currentKey)) continue;
      if (currentKey === endKey) break;
      closed.add(currentKey);
      directions.forEach(([di, dj, moveCost]) => {
        const i = current.i + di;
        const j = current.j + dj;
        if (i < 0 || j < 0 || i > maxI || j > maxJ) return;
        const nextKey = key(i, j);
        if (closed.has(nextKey)) return;
        const point = toPoint({i, j});
        if (nextKey !== endKey && nextKey !== startKey &&
            this.isNavigationBlocked(point.x, point.z, actor)) return;
        if (di && dj) {
          const sideA = toPoint({i: current.i + di, j: current.j});
          const sideB = toPoint({i: current.i, j: current.j + dj});
          if (this.isNavigationBlocked(sideA.x, sideA.z, actor) ||
              this.isNavigationBlocked(sideB.x, sideB.z, actor)) return;
        }
        const nextCost = current.g + moveCost;
        if (nextCost >= (costs.get(nextKey) ?? Number.POSITIVE_INFINITY)) return;
        costs.set(nextKey, nextCost);
        parents.set(nextKey, currentKey);
        const heuristic = Math.hypot(endCell.i - i, endCell.j - j);
        open.push({i, j, g: nextCost, f: nextCost + heuristic});
      });
    }

    if (!parents.has(endKey)) {
      return [];
    }
    const cells = [];
    let cursor = endKey;
    while (cursor !== startKey) {
      const [i, j] = cursor.split(":").map(Number);
      cells.push(toPoint({i, j}));
      cursor = parents.get(cursor);
      if (!cursor) break;
    }
    cells.reverse();
    const raw = [...cells, new THREE.Vector3(target.x, 0, target.z)];
    const smoothed = [];
    let anchor = start;
    let index = 0;
    while (index < raw.length) {
      let farthest = index;
      for (let candidate = raw.length - 1; candidate >= index; candidate -= 1) {
        if (this.lineOfSight(anchor, raw[candidate], actor)) {
          farthest = candidate;
          break;
        }
      }
      const next = raw[farthest];
      smoothed.push(next);
      anchor = next;
      index = farthest + 1;
    }
    return smoothed;
  }

  lineOfSight(start, end, actor) {
    const distance = Math.hypot(end.x - start.x, end.z - start.z);
    const samples = Math.max(2, Math.ceil(distance / 0.22));
    for (let index = 1; index < samples; index += 1) {
      const amount = index / samples;
      const x = start.x + (end.x - start.x) * amount;
      const z = start.z + (end.z - start.z) * amount;
      if (this.isNavigationBlocked(x, z, actor)) return false;
    }
    return true;
  }

  isNavigationBlocked(x, z, actor) {
    if (x < -11.35 || x > 11.35 || z < -7.35 || z > 7.35) return true;
    if ((x * x) / (2.78 * 2.78) + (z * z) / (2.48 * 2.48) < 1) return true;
    for (const [name, layout] of Object.entries(DESKS)) {
      const dx = x - layout[0];
      const dz = z - layout[1];
      const cosine = Math.cos(layout[2]);
      const sine = Math.sin(layout[2]);
      const localX = dx * cosine - dz * sine;
      const localZ = dx * sine + dz * cosine;
      if (Math.abs(localX) < 1.82 && Math.abs(localZ) < 0.91) return true;
      if ((!actor || actor.name !== name) &&
          Math.abs(localX) < 0.62 && Math.abs(localZ - 1.22) < 0.62) return true;
    }
    if (x > -9.85 && x < -6.55 && z > 6.55) return true;
    if (x > 10.45 && z < -6.15) return true;
    if (Math.hypot(x + 11.2, z + 6.8) < 0.58) return true;
    if (Math.hypot(x - 11.1, z - 6.7) < 0.58) return true;
    return false;
  }

  walkTo(actor, target, arrivalMode, arrivalYaw) {
    actor.route = this.buildRoute(actor.root.position, target, actor);
    if (!actor.route.length) {
      actor.mode = "standing";
      actor.blockedFor = 0;
      return false;
    }
    actor.mode = "walking";
    actor.arrivalMode = arrivalMode || "standing";
    actor.arrivalYaw = arrivalYaw == null ? actor.root.rotation.y : arrivalYaw;
    actor.blockedFor = 0;
    actor.speech.classList.remove("visible");
    return true;
  }

  walkingDirection(actor, dx, dz, distance, delta) {
    let x = dx / distance;
    let z = dz / distance;
    this.agents.forEach((other) => {
      if (other === actor) return;
      const awayX = actor.root.position.x - other.root.position.x;
      const awayZ = actor.root.position.z - other.root.position.z;
      const separation = Math.hypot(awayX, awayZ);
      if (separation >= 1.35) return;
      const strength = (1.35 - Math.max(separation, 0.05)) / 1.35;
      if (separation > 0.05) {
        x += awayX / separation * strength * 1.8;
        z += awayZ / separation * strength * 1.8;
      }
      const approaching = x * -awayX + z * -awayZ > 0;
      if (approaching && separation < 1.05) {
        const sideX = -dz / distance;
        const sideZ = dx / distance;
        x += sideX * strength * 1.45;
        z += sideZ * strength * 1.45;
      }
    });
    const length = Math.hypot(x, z) || 1;
    x /= length;
    z /= length;
    actor.velocity.x = damp(actor.velocity.x, x, 9, delta);
    actor.velocity.y = damp(actor.velocity.y, z, 9, delta);
    const velocityLength = Math.hypot(actor.velocity.x, actor.velocity.y) || 1;
    return {
      x: actor.velocity.x / velocityLength,
      z: actor.velocity.y / velocityLength
    };
  }

  positionIsClear(actor, x, z) {
    if (this.isNavigationBlocked(x, z, actor)) return false;
    for (const other of this.agents.values()) {
      if (other === actor) continue;
      if (Math.hypot(x - other.root.position.x, z - other.root.position.z) < PERSONAL_SPACE) {
        return false;
      }
    }
    return true;
  }

  addSidestep(actor, target) {
    const dx = target.x - actor.root.position.x;
    const dz = target.z - actor.root.position.z;
    const distance = Math.hypot(dx, dz);
    if (distance < 0.05) return false;
    const sideX = -dz / distance;
    const sideZ = dx / distance;
    const forwardX = dx / distance;
    const forwardZ = dz / distance;
    const preferred = ROLE_ORDER.indexOf(actor.name) % 2 ? -1 : 1;
    for (const sign of [preferred, -preferred]) {
      const detour = new THREE.Vector3(
        actor.root.position.x + sideX * sign * 0.88 + forwardX * 0.24,
        0,
        actor.root.position.z + sideZ * sign * 0.88 + forwardZ * 0.24
      );
      if (this.positionIsClear(actor, detour.x, detour.z) &&
          this.lineOfSight(actor.root.position, detour, actor)) {
        actor.route.unshift(detour);
        actor.velocity.set(0, 0);
        actor.blockedFor = 0;
        return true;
      }
    }
    return false;
  }

  returnHome(actor) {
    this.walkTo(actor, actor.home, actor.data.status === "working" ? "working" : "sitting", actor.homeYaw);
  }

  isBusy(actor) {
    return actor.mode === "walking" || actor.mode === "talking" || actor.actionUntil > performance.now();
  }

  animateHandoff(handoffs) {
    const handoff = Array.from(handoffs).reverse().find((item) =>
      item.agent && item.next_agent && this.agents.has(item.agent) && this.agents.has(item.next_agent)
    );
    if (!handoff) return;
    const key = this.projectId + ":" + handoff.sequence;
    if (key === this.lastHandoff) return;
    this.lastHandoff = key;
    if (this.motionPaused) return;
    window.setTimeout(() => {
      if (!this.motionPaused && this.projectId === payloadProject(key)) {
        this.startConversation(
          handoff.agent,
          handoff.next_agent,
          "Handoff: " + String(handoff.summary || "Context is ready.").slice(0, 112),
          "Context received. I’ll take it from here.",
          true
        );
      }
    }, 850);
  }

  startConversation(firstName, secondName, firstLine, secondLine, isHandoff) {
    if (this.motionPaused || firstName === secondName) return;
    if (isHandoff && this.conversation) this.finishConversation();
    if (this.conversation) return;
    const first = this.agents.get(firstName);
    const second = this.agents.get(secondName);
    if (!first || !second) return;
    if (!isHandoff && (this.isBusy(first) || this.isBusy(second))) return;
    if (isHandoff) {
      [first, second].forEach((actor) => {
        actor.route.length = 0;
        actor.actionUntil = 0;
        actor.onArrival = null;
      });
    }
    const spot = MEETING_POINTS[Math.floor(Math.random() * MEETING_POINTS.length)];
    const horizontal = Math.abs(spot[0]) > Math.abs(spot[1]);
    const offset = horizontal ? [0, 0.82] : [0.82, 0];
    const aTarget = new THREE.Vector3(spot[0] - offset[0], 0, spot[1] - offset[1]);
    const bTarget = new THREE.Vector3(spot[0] + offset[0], 0, spot[1] + offset[1]);
    const aYaw = Math.atan2(bTarget.x - aTarget.x, bTarget.z - aTarget.z);
    const bYaw = Math.atan2(aTarget.x - bTarget.x, aTarget.z - bTarget.z);
    this.conversation = {
      first: first, second: second, arrived: new Set(), started: 0,
      firstLine: firstLine, secondLine: secondLine,
      duration: isHandoff ? 6.2 : 5.0
    };
    first.onArrival = () => this.arriveConversation(first, aYaw);
    second.onArrival = () => this.arriveConversation(second, bYaw);
    const firstCanMeet = this.walkTo(first, aTarget, "standing", aYaw);
    const secondCanMeet = this.walkTo(second, bTarget, "standing", bYaw);
    if (!firstCanMeet || !secondCanMeet) {
      this.conversation = null;
      [first, second].forEach((actor) => {
        actor.onArrival = null;
        this.returnHome(actor);
      });
      this.setActivity("The meeting route was busy, so the team returned to their desks.");
      return;
    }
    this.setActivity(
      (first.data.label || first.name) + " and " + (second.data.label || second.name) +
      (isHandoff ? " are transferring context." : " are comparing notes.")
    );
  }

  arriveConversation(actor, yaw) {
    if (!this.conversation) return;
    actor.root.rotation.y = yaw;
    actor.mode = "standing";
    this.conversation.arrived.add(actor.name);
    if (this.conversation.arrived.size < 2) return;
    const talk = this.conversation;
    talk.started = performance.now();
    talk.first.mode = "talking";
    talk.second.mode = "talking";
    talk.first.speech.textContent = talk.firstLine;
    talk.second.speech.textContent = talk.secondLine;
    talk.first.speech.classList.add("visible");
    talk.second.speech.classList.add("visible");
  }

  finishConversation() {
    if (!this.conversation) return;
    const talk = this.conversation;
    [talk.first, talk.second].forEach((actor) => {
      actor.speech.classList.remove("visible");
      actor.speech.textContent = "";
      this.returnHome(actor);
    });
    this.conversation = null;
    this.setActivity("The team is moving between desks, the task rail, and the shared table.");
  }

  scheduleBehavior(nowSeconds) {
    if (this.motionPaused || this.conversation || nowSeconds - this.lastBehavior < this.nextBehavior) return;
    this.lastBehavior = nowSeconds;
    this.nextBehavior = 5.5 + Math.random() * 3.5;
    const available = Array.from(this.agents.values()).filter((actor) =>
      actor.data.status !== "working" && !["error", "stopped"].includes(actor.data.status) && !this.isBusy(actor)
    );
    if (!available.length) return;
    shuffle(available);
    if (available.length > 1 && Math.random() < 0.42) {
      this.startConversation(
        available[0].name, available[1].name,
        ROOM_LINES[available[0].name], ROOM_LINES[available[1].name], false
      );
      return;
    }
    available.slice(0, Math.min(2, available.length)).forEach((actor, index) => {
      const point = WANDER_POINTS[Math.floor(Math.random() * WANDER_POINTS.length)];
      const target = new THREE.Vector3(
        point[0] + (Math.random() - 0.5) * 0.7,
        0,
        point[1] + (Math.random() - 0.5) * 0.7
      );
      actor.onArrival = () => {
        actor.mode = "standing";
        actor.actionUntil = performance.now() + 1700 + index * 400;
      };
      this.walkTo(actor, target, "standing", actor.root.rotation.y);
    });
  }

  updateActor(actor, delta, elapsed) {
    if (actor.mode === "walking" && !this.motionPaused) {
      const target = actor.route[0];
      if (target) {
        const dx = target.x - actor.root.position.x;
        const dz = target.z - actor.root.position.z;
        const distance = Math.hypot(dx, dz);
        let step = Math.min(distance, WALK_SPEED * delta);
        if (distance > 0.001) {
          const direction = this.walkingDirection(actor, dx, dz, distance, delta);
          let nextX = actor.root.position.x + direction.x * step;
          let nextZ = actor.root.position.z + direction.z * step;
          if (!this.positionIsClear(actor, nextX, nextZ)) {
            const directX = actor.root.position.x + dx / distance * step;
            const directZ = actor.root.position.z + dz / distance * step;
            if (this.positionIsClear(actor, directX, directZ)) {
              nextX = directX;
              nextZ = directZ;
            } else {
              step = 0;
              actor.blockedFor += delta;
              if (actor.blockedFor > 0.55) this.addSidestep(actor, target);
            }
          } else {
            actor.blockedFor = 0;
          }
          if (step > 0) {
            actor.root.position.x = nextX;
            actor.root.position.z = nextZ;
            const targetYaw = Math.atan2(direction.x, direction.z);
            actor.root.rotation.y = this.dampAngle(actor.root.rotation.y, targetYaw, 10, delta);
            actor.walkPhase += step * 7.4;
          }
        }
        if (actor.route[0] === target && distance < 0.035 &&
            this.positionIsClear(actor, target.x, target.z)) {
          actor.root.position.x = target.x;
          actor.root.position.z = target.z;
          actor.route.shift();
          if (!actor.route.length) {
            actor.mode = actor.arrivalMode;
            actor.root.rotation.y = actor.arrivalYaw;
            if (actor.onArrival) {
              const callback = actor.onArrival;
              actor.onArrival = null;
              callback();
            }
          }
        }
      }
    } else if (!this.motionPaused && actor.mode === "standing" && actor.actionUntil &&
               performance.now() > actor.actionUntil) {
      actor.actionUntil = 0;
      this.returnHome(actor);
    }
    this.applyPose(actor, delta, elapsed);
  }

  applyPose(actor, delta, elapsed) {
    const joints = actor.joints;
    const target = {
      leftHip: 0, rightHip: 0, leftKnee: 0, rightKnee: 0,
      leftAnkle: 0, rightAnkle: 0,
      leftShoulder: 0, rightShoulder: 0, leftElbow: 0, rightElbow: 0
    };
    let rootY = 0;

    if (actor.mode === "sitting" || actor.mode === "working") {
      rootY = SIT_ROOT_Y;
      target.leftHip = -Math.PI / 2;
      target.rightHip = -Math.PI / 2;
      target.leftKnee = Math.PI / 2;
      target.rightKnee = Math.PI / 2;
      target.leftShoulder = -0.82;
      target.rightShoulder = -0.82;
      target.leftElbow = -0.62;
      target.rightElbow = -0.62;
      if (actor.mode === "working" && !this.motionPaused) {
        const typing = Math.sin(elapsed * 9 + ROLE_ORDER.indexOf(actor.name)) * 0.10;
        target.leftShoulder += typing;
        target.rightShoulder -= typing;
      }
    } else if (actor.mode === "walking" && !this.motionPaused) {
      const stride = Math.sin(actor.walkPhase) * 0.62;
      target.leftHip = stride;
      target.rightHip = -stride;
      target.leftKnee = Math.max(0, -stride) * 0.78;
      target.rightKnee = Math.max(0, stride) * 0.78;
      target.leftShoulder = -stride * 0.72;
      target.rightShoulder = stride * 0.72;
      target.leftElbow = 0.08;
      target.rightElbow = 0.08;
      rootY = Math.abs(Math.sin(actor.walkPhase * 2)) * 0.035;
    } else if (actor.mode === "talking" && !this.motionPaused) {
      const gesture = (Math.sin(elapsed * 3.4 + ROLE_ORDER.indexOf(actor.name)) + 1) * 0.16;
      target.rightShoulder = -0.45 - gesture;
      target.rightElbow = -0.52 - gesture * 0.35;
      target.leftShoulder = -0.1;
      target.leftElbow = -0.08;
    }

    target.leftAnkle = -(target.leftHip + target.leftKnee);
    target.rightAnkle = -(target.rightHip + target.rightKnee);

    actor.root.position.y = damp(actor.root.position.y, rootY, 11, delta);
    Object.keys(target).forEach((name) => {
      joints[name].rotation.x = damp(joints[name].rotation.x, target[name], 12, delta);
    });
  }

  dampAngle(current, target, lambda, delta) {
    const twoPi = Math.PI * 2;
    let difference = (target - current + Math.PI) % twoPi - Math.PI;
    if (difference < -Math.PI) difference += twoPi;
    return current + difference * (1 - Math.exp(-lambda * delta));
  }

  updateConversation(now) {
    if (!this.conversation || !this.conversation.started) return;
    if (now - this.conversation.started > this.conversation.duration * 1000) {
      this.finishConversation();
    }
  }

  updateLabels() {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    const point = new THREE.Vector3();
    this.agents.forEach((actor) => {
      actor.anchor.getWorldPosition(point);
      point.project(this.camera);
      const visible = point.z > -1 && point.z < 1 &&
        point.x > -1.12 && point.x < 1.12 && point.y > -1.12 && point.y < 1.12;
      actor.label.hidden = !visible;
      actor.speech.hidden = !visible;
      if (!visible) return;
      const x = (point.x * 0.5 + 0.5) * width;
      const y = (-point.y * 0.5 + 0.5) * height;
      actor.label.style.transform = "translate(-50%, -50%) translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px)";
      actor.speech.style.transform = "translate(-50%, -100%) translate(" + x.toFixed(1) + "px," + (y - 25).toFixed(1) + "px)";
    });
  }

  animate(time) {
    if (!this.renderer || this.contextLost) return;
    if (!this.isVisible) return;
    const minFrame = 1000 / 30;
    if (time - this.lastFrame < minFrame) return;
    const delta = Math.min((time - this.lastFrame) / 1000 || 0, 0.05);
    this.lastFrame = time;
    const elapsed = time / 1000;
    if (!this.motionPaused) {
      this.agents.forEach((actor) => this.updateActor(actor, delta, elapsed));
      this.updateConversation(performance.now());
      this.scheduleBehavior(elapsed);
      this.needsRender = true;
    }
    if (!this.needsRender) return;
    this.renderer.render(this.scene, this.camera);
    this.updateLabels();
    this.needsRender = false;
  }

  resize() {
    if (!this.renderer) return;
    const width = Math.max(1, this.container.clientWidth);
    const height = Math.max(1, this.container.clientHeight);
    const pixelRatio = Math.min(window.devicePixelRatio || 1, width < 700 ? 1.25 : 1.5);
    if (this.renderer.getPixelRatio() !== pixelRatio) this.renderer.setPixelRatio(pixelRatio);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.needsRender = true;
  }

  updateCamera() {
    const horizontal = Math.cos(this.cameraPitch) * this.cameraRadius;
    this.camera.position.set(
      this.cameraTarget.x + Math.sin(this.cameraYaw) * horizontal,
      this.cameraTarget.y + Math.sin(this.cameraPitch) * this.cameraRadius,
      this.cameraTarget.z + Math.cos(this.cameraYaw) * horizontal
    );
    this.camera.lookAt(this.cameraTarget);
    this.needsRender = true;
  }

  bindControls() {
    const canvas = this.renderer.domElement;
    canvas.tabIndex = 0;
    canvas.addEventListener("pointerdown", (event) => {
      this.drag = {x: event.clientX, y: event.clientY, yaw: this.cameraYaw, pitch: this.cameraPitch};
      this.pointerMoved = false;
      canvas.classList.add("dragging");
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!this.drag) return;
      const dx = event.clientX - this.drag.x;
      const dy = event.clientY - this.drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) this.pointerMoved = true;
      this.cameraYaw = this.drag.yaw - dx * 0.006;
      this.cameraPitch = clamp(this.drag.pitch + dy * 0.004, 0.28, 1.05);
      this.updateCamera();
    });
    const release = (event) => {
      if (!this.drag) return;
      if (!this.pointerMoved) this.pick(event);
      this.drag = null;
      canvas.classList.remove("dragging");
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    };
    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);
    canvas.addEventListener("wheel", (event) => {
      event.preventDefault();
      this.cameraRadius = clamp(this.cameraRadius + event.deltaY * 0.016, 15, 37);
      this.updateCamera();
    }, {passive: false});
    canvas.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "+", "=", "-", "_", "Home"].includes(event.key)) {
        return;
      }
      event.preventDefault();
      if (event.key === "ArrowLeft") this.cameraYaw += 0.12;
      if (event.key === "ArrowRight") this.cameraYaw -= 0.12;
      if (event.key === "ArrowUp") this.cameraPitch = clamp(this.cameraPitch - 0.08, 0.28, 1.05);
      if (event.key === "ArrowDown") this.cameraPitch = clamp(this.cameraPitch + 0.08, 0.28, 1.05);
      if (event.key === "+" || event.key === "=") this.cameraRadius = clamp(this.cameraRadius - 1.2, 15, 37);
      if (event.key === "-" || event.key === "_") this.cameraRadius = clamp(this.cameraRadius + 1.2, 15, 37);
      if (event.key === "Home") {
        this.cameraYaw = 0.70;
        this.cameraPitch = 0.58;
        this.cameraRadius = 27;
      }
      this.updateCamera();
    });
  }

  pick(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.x = (event.clientX - rect.left) / rect.width * 2 - 1;
    this.pointer.y = -(event.clientY - rect.top) / rect.height * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObjects(this.clickables, false)[0];
    if (hit && hit.object.userData.agent) this.openAgent(hit.object.userData.agent);
  }

  openAgent(name) {
    if (typeof window.openAgent === "function") window.openAgent(name);
  }

  toggleMotion() {
    this.motionPaused = !this.motionPaused;
    if (this.motionPaused) {
      if (this.conversation) this.finishConversation();
      this.agents.forEach((actor) => {
        actor.route.length = 0;
        if (actor.mode === "walking" || actor.mode === "talking" || actor.mode === "standing") {
          actor.root.position.x = actor.home.x;
          actor.root.position.z = actor.home.z;
          actor.mode = actor.data.status === "working" ? "working" : "sitting";
        }
        actor.onArrival = null;
        actor.actionUntil = 0;
        actor.velocity.set(0, 0);
        actor.blockedFor = 0;
        this.applyPose(actor, 1, 0);
      });
      this.setActivity("Room movement paused. Research execution is unaffected.");
    } else {
      this.lastBehavior = performance.now() / 1000 - 4;
      this.setActivity("Room movement resumed at a human walking pace.");
    }
    this.updateMotionButton();
    this.needsRender = true;
    return this.motionPaused;
  }

  updateMotionButton() {
    const button = document.querySelector("#motion-toggle");
    if (button) {
      button.textContent = this.motionPaused ? "Resume movement" : "Pause movement";
      button.setAttribute("aria-pressed", String(this.motionPaused));
    }
  }

  setActivity(text) {
    if (this.activity) this.activity.textContent = text;
  }

  setTheme(settings) {
    if (!this.renderer || !settings) return;
    this.theme = settings;
    const background = cssColor(settings.bg, "#08110f");
    const floor = cssColor(settings.floor, "#14241f");
    const wall = cssColor(settings.wall, "#24443b");
    this.renderer.setClearColor(background, 1);
    this.scene.background = background;
    this.scene.fog.color.copy(background);
    this.materials.floor.color.copy(floor);
    this.materials.wall.color.copy(wall);
    this.materials.wallSide.color.copy(wall).multiplyScalar(0.78);
    const light = clamp(Number(settings.light || 100) / 100, 0.55, 1.35);
    this.hemi.intensity = 2.25 * light;
    this.keyLight.intensity = 2.1 * light;
    this.needsRender = true;
  }

  showFallback(error) {
    this.container.innerHTML =
      '<div class="room-fallback"><b>3D office unavailable</b>' +
      "<span>This browser could not start WebGL. You can still open every agent desk below.</span>" +
      '<div class="room-fallback-agents"></div></div>';
    const list = this.container.querySelector(".room-fallback-agents");
    STAGES.forEach((entry) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = entry[0];
      button.addEventListener("click", () => this.openAgent(entry[1]));
      list.appendChild(button);
    });
    const support = this.detectWebGLSupport();
    const diagnostic = document.createElement("small");
    diagnostic.className = "room-fallback-diagnostic";
    diagnostic.textContent =
      "WebGL2: " + (support.webgl2 ? "available" : "unavailable") +
      " · WebGL1: " + (support.webgl1 ? "available" : "unavailable") +
      " · " + String(error.message || error).slice(0, 280);
    this.container.querySelector(".room-fallback").appendChild(diagnostic);
    console.error("OpenFARS 3D office failed to start", error);
  }

  detectWebGLSupport() {
    function available(name) {
      try {
        return Boolean(document.createElement("canvas").getContext(name));
      } catch (_) {
        return false;
      }
    }
    return {webgl2: available("webgl2"), webgl1: available("webgl")};
  }

  inspectScene() {
    let minimumSeparation = Number.POSITIVE_INFINITY;
    const actors = Array.from(this.agents.values());
    for (let first = 0; first < actors.length; first += 1) {
      for (let second = first + 1; second < actors.length; second += 1) {
        minimumSeparation = Math.min(minimumSeparation, Math.hypot(
          actors[first].root.position.x - actors[second].root.position.x,
          actors[first].root.position.z - actors[second].root.position.z
        ));
      }
    }
    const modes = {};
    actors.forEach((actor) => {
      modes[actor.mode] = (modes[actor.mode] || 0) + 1;
    });
    return {
      renderer: Boolean(this.renderer),
      agents: actors.length,
      projectId: this.projectId,
      paused: this.motionPaused,
      visible: this.isVisible,
      rendererProfile: this.rendererProfile || "unavailable",
      pixelRatio: this.renderer ? this.renderer.getPixelRatio() : 0,
      walkSpeed: WALK_SPEED,
      personalSpace: PERSONAL_SPACE,
      mice: this.desks.size,
      chairSeatClearance: Number((
        SIT_ROOT_Y + PELVIS_BOTTOM_FROM_ROOT -
        (CHAIR_SEAT_Y + CHAIR_SEAT_HEIGHT / 2)
      ).toFixed(3)),
      chairBackClearance: Number((
        CHAIR_BACK_Z - CHAIR_BACK_THICKNESS / 2 - TORSO_BACK_RADIUS
      ).toFixed(3)),
      minimumAgentSeparation: Number.isFinite(minimumSeparation) ? minimumSeparation : null,
      modes: modes,
      blockedAgents: actors.filter((actor) => actor.blockedFor > 0.55).length,
      navigationViolations: actors.filter((actor) =>
        actor.mode === "walking" && this.isNavigationBlocked(
          actor.root.position.x, actor.root.position.z, actor
        )
      ).length,
      drawCalls: this.renderer ? this.renderer.info.render.calls : 0,
      triangles: this.renderer ? this.renderer.info.render.triangles : 0,
      geometries: this.renderer ? this.renderer.info.memory.geometries : 0,
      textures: this.renderer ? this.renderer.info.memory.textures : 0,
      programs: this.renderer ? this.renderer.info.programs.length : 0,
      renderFrame: this.renderer ? this.renderer.info.render.frame : 0,
      contextLost: this.contextLost
    };
  }
}

function shuffle(items) {
  for (let index = items.length - 1; index > 0; index -= 1) {
    const other = Math.floor(Math.random() * (index + 1));
    const value = items[index];
    items[index] = items[other];
    items[other] = value;
  }
  return items;
}

function payloadProject(key) {
  return String(key).split(":")[0];
}

const container = document.querySelector("#office-room");
if (container) {
  const office = new Office3D(container);
  window.OpenFARS3D = {
    setProject: (payload) => office.setProject(payload),
    setTheme: (settings) => office.setTheme(settings),
    toggleMotion: () => office.toggleMotion(),
    inspect: () => office.inspectScene()
  };
  if (window.__openfars3dPending) office.setProject(window.__openfars3dPending);
  if (window.__openfars3dTheme) office.setTheme(window.__openfars3dTheme);
  window.dispatchEvent(new CustomEvent("openfars3d-ready"));
}
