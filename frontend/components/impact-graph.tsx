"use client";

import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Node,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import { Box, Database, KeyRound, Network, Shield, ShoppingCart, Wallet, Bell } from "lucide-react";
import type { Dependency, RepoModule, RiskLevel } from "@/lib/types";

const ICONS: Record<string, typeof Box> = {
  auth: KeyRound,
  payments: Wallet,
  gateway: Network,
  orders: ShoppingCart,
  database: Database,
  fraud: Shield,
  notifications: Bell,
};

interface ModuleNodeData extends Record<string, unknown> {
  module: RepoModule;
  impacted: boolean;
  focused: boolean;
}

type ModuleNode = Node<ModuleNodeData, "module">;

function CustomModuleNode({ data }: NodeProps<ModuleNode>) {
  const module = data.module;
  const Icon = ICONS[module.id] || Box;
  return (
    <div className={`flow-node ${module.importance.toLowerCase()} ${data.impacted ? "flow-node-impacted" : ""} ${data.focused ? "flow-node-focused" : ""}`}>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <div className="flow-node-header">
        <span className="flow-node-icon"><Icon size={16} strokeWidth={2} /></span>
        <span className={`mini-pill ${module.importance.toLowerCase()}`}>{module.importance}</span>
      </div>
      <div className="flow-node-name">{module.name}</div>
      <div className="flow-node-file">{module.path.split("/").slice(-2).join("/")}</div>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}

const nodeTypes = { module: CustomModuleNode };

export function ImpactGraph({
  modules,
  dependencies,
  impactedIds = [],
  selectedId,
  onSelect,
}: {
  modules: RepoModule[];
  dependencies: Dependency[];
  impactedIds?: string[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}) {
  const affected = useMemo(() => new Set(impactedIds), [impactedIds]);
  const nodes = useMemo<ModuleNode[]>(() => modules.map((module) => ({
    id: module.id,
    type: "module",
    position: module.position,
    data: { module, impacted: affected.has(module.id), focused: module.id === selectedId },
    draggable: false,
    selectable: true,
  })), [modules, affected, selectedId]);

  const edges = useMemo<Edge[]>(() => dependencies.map((dep, index) => ({
    id: `edge-${index}`,
    source: dep.source,
    target: dep.target,
    animated: affected.has(dep.source) && affected.has(dep.target),
    type: "smoothstep",
    style: {
      stroke: affected.has(dep.source) && affected.has(dep.target) ? "#f59e74" : "#35506c",
      strokeWidth: affected.has(dep.source) && affected.has(dep.target) ? 2.1 : 1.2,
      opacity: affected.size > 0 && !(affected.has(dep.source) && affected.has(dep.target)) ? 0.35 : 0.86,
    },
  })), [dependencies, affected]);

  if (modules.length === 0) return <div className="graph-empty">No module graph available for this repository.</div>;

  return (
    <div className="flow-canvas" aria-label="Interactive repository dependency graph">
      <ReactFlow<ModuleNode, Edge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.18, maxZoom: 1.1 }}
        minZoom={0.35}
        maxZoom={1.8}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, node) => onSelect?.(node.id)}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#263c58" gap={24} size={1} />
        <Controls position="bottom-left" showInteractive={false} />
        <MiniMap position="bottom-right" pannable zoomable nodeStrokeWidth={2} nodeColor={(node) => {
          const level = (node.data as ModuleNodeData)?.module.importance as RiskLevel;
          if (level === "CRITICAL") return "#f78383";
          if (level === "HIGH") return "#f5b86f";
          return "#6689b3";
        }} />
      </ReactFlow>
    </div>
  );
}
