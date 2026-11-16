"use client";

import { useEffect, useRef } from "react";
import type L from "leaflet";
import * as d3 from "d3";
import { edgeId, nodeId, type CausalLink, type Discovery, type Domain } from "@/lib/api";

export const DOMAIN_COLOR: Record<Domain, string> = {
  atmosphere: "#fb7185", hydro: "#38bdf8", cryo: "#e2e8f0", bio: "#4ade80",
};
type Node = d3.SimulationNodeDatum & { id: string; item: Discovery; homeX: number; homeY: number };
type Edge = d3.SimulationLinkDatum<Node> & { link: CausalLink };
type Props = { map: L.Map | null; discoveries: Discovery[]; links: CausalLink[]; selectedEdge: CausalLink | null; onEdgeSelect: (edge: CausalLink) => void };

export default function CausalGraph({ map, discoveries, links, selectedEdge, onEdgeSelect }: Props) {
  const selection = useRef(selectedEdge);
  const callback = useRef(onEdgeSelect);
  useEffect(() => { selection.current = selectedEdge; callback.current = onEdgeSelect; }, [selectedEdge, onEdgeSelect]);

  useEffect(() => {
    if (!map || !links.length) return;
    const ids = new Set(links.flatMap((link) => [link.cause, link.effect]));
    const nodes: Node[] = discoveries.filter((item) => ids.has(nodeId(item))).map((item) => ({ id: nodeId(item), item, homeX: 0, homeY: 0 }));
    const edges: Edge[] = links.map((link) => ({ source: link.cause, target: link.effect, link }));
    const svg = d3.select(map.getContainer()).append("svg")
      .attr("class", "causal-graph-overlay").attr("aria-label", "Discovered statistical association graph")
      .style("position", "absolute").style("inset", "0").style("width", "100%")
      .style("height", "100%").style("pointer-events", "none").style("z-index", "450");
    svg.append("defs").append("marker").attr("id", "causal-arrow").attr("viewBox", "0 -5 10 10")
      .attr("refX", 10).attr("refY", 0).attr("markerWidth", 5).attr("markerHeight", 5).attr("orient", "auto")
      .append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", "#bae6fd");
    const paths = svg.append("g").selectAll("path").data(edges).join("path")
      .attr("class", "causal-link").attr("fill", "none").attr("marker-end", "url(#causal-arrow)")
      .style("pointer-events", "stroke").style("cursor", "pointer")
      .attr("tabindex", 0).attr("role", "button")
      .attr("aria-label", (edge) => `${edge.link.cause} to ${edge.link.effect}, lag ${edge.link.lag} months`)
      .on("click", (event, edge) => { event.stopPropagation(); callback.current(edge.link); })
      .on("keydown", (event, edge) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); callback.current(edge.link); } });
    paths.append("title").text((edge) => `${edge.link.cause} → ${edge.link.effect}\nLag ${edge.link.lag} months · r=${edge.link.strength.toFixed(3)} · p=${edge.link.p_value.toPrecision(3)}`);
    const labels = svg.append("g").selectAll("text").data(edges).join("text")
      .attr("text-anchor", "middle").attr("fill", "#e0f2fe").attr("font-size", 11)
      .attr("stroke", "#071018").attr("stroke-width", 4).attr("paint-order", "stroke")
      .text((edge) => `${edge.link.lag}m`);
    const nodeGroups = svg.append("g").selectAll("g").data(nodes).join("g").attr("class", "causal-node");
    nodeGroups.append("circle").attr("r", 9).attr("fill", (node) => DOMAIN_COLOR[node.item.domain]).attr("stroke", "white");
    nodeGroups.append("text").attr("x", 13).attr("y", 4).attr("fill", "white").attr("font-size", 12)
      .attr("stroke", "#071018").attr("stroke-width", 4).attr("paint-order", "stroke").text((node) => node.item.label);
    const position = () => {
      nodes.forEach((node, i) => {
        const point = map.latLngToContainerPoint([node.item.lat, node.item.lon]);
        const angle = (i / nodes.length) * Math.PI * 2;
        node.homeX = point.x + Math.cos(angle) * 85;
        node.homeY = point.y + Math.sin(angle) * 85;
      });
    };
    position();
    nodes.forEach((node) => { node.x = node.homeX; node.y = node.homeY; });
    const tick = () => {
      paths.attr("stroke", (edge) => edgeId(selection.current ?? edge.link) === edgeId(edge.link) && selection.current ? "#fbbf24" : edge.link.strength < 0 ? "#fb7185" : "#7dd3fc")
        .attr("stroke-width", (edge) => 2 + Math.abs(edge.link.strength) * 4)
        .attr("d", (edge) => {
          const s = edge.source as Node, t = edge.target as Node;
          const x = s.x!, y = s.y!, tx = t.x!, ty = t.y!;
          if (s === t) { const r = 25 + edge.link.lag * 6; return `M${x - 5},${y - 8} C${x - r * 2},${y - r * 2} ${x + r * 2},${y - r * 2} ${x + 5},${y - 8}`; }
          const dx = tx - x, dy = ty - y, length = Math.hypot(dx, dy) || 1;
          const bend = 15 + edge.link.lag * 9;
          return `M${x},${y} Q${(x + tx) / 2 - dy / length * bend},${(y + ty) / 2 + dx / length * bend} ${tx - dx / length * 12},${ty - dy / length * 12}`;
        });
      labels.attr("x", (edge) => ((edge.source as Node).x! + (edge.target as Node).x!) / 2)
        .attr("y", (edge) => { const s = edge.source as Node, t = edge.target as Node; return s === t ? s.y! - (25 + edge.link.lag * 6) * 1.5 : (s.y! + t.y!) / 2 - 8 - edge.link.lag * 3; });
      nodeGroups.attr("transform", (node) => `translate(${node.x},${node.y})`);
    };
    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink<Node, Edge>(edges).id((node) => node.id).distance(150).strength(0.1))
      .force("x", d3.forceX<Node>((node) => node.homeX).strength(0.4))
      .force("y", d3.forceY<Node>((node) => node.homeY).strength(0.4))
      .force("collide", d3.forceCollide<Node>(42)).on("tick", tick);
    const reset = () => {
      position();
      simulation.force("x", d3.forceX<Node>((node) => node.homeX).strength(0.4));
      simulation.force("y", d3.forceY<Node>((node) => node.homeY).strength(0.4));
      simulation.alpha(0.7).restart();
    };
    map.on("move zoom resize", reset);
    const highlight = window.setInterval(tick, 250);
    return () => { window.clearInterval(highlight); map.off("move zoom resize", reset); simulation.stop(); svg.remove(); };
  }, [map, discoveries, links]);
  return null;
}
