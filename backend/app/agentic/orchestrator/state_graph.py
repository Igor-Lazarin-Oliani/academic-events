"""Orquestração como grafo de estados explícito.

Cada nó é uma função (estado) -> próximo nó. Depois de cada transição o estado é gravado
(checkpoint), então dá para pausar (ex.: HUMAN_APPROVAL), retomar e ver o caminho percorrido."""

from dataclasses import dataclass
from typing import Callable

from app.agentic.tracing import RunRecorder


class GraphError(Exception):
    pass


@dataclass
class StateGraph:
    name: str
    nodes: dict[str, Callable[[dict], str]]
    transitions: dict[str, set[str]]  # transições permitidas (validadas em tempo de execução)
    start: str
    terminal: set[str]
    pause: set[str]  # estados em que a execução para e espera um humano
    max_transitions: int = 25

    def run(self, state: dict, recorder: RunRecorder, *, start_at: str | None = None) -> str:
        node = start_at or self.start
        recorder.checkpoint(node, state)
        for _ in range(self.max_transitions):
            if node in self.terminal or node in self.pause:
                return node
            fn = self.nodes.get(node)
            if fn is None:
                raise GraphError(f"node {node} has no handler")
            nxt = fn(state)
            if nxt not in self.transitions.get(node, set()):
                raise GraphError(f"invalid transition {node} -> {nxt}")
            recorder.step("transition", f"{node}->{nxt}", agent=self.name)
            state.setdefault("path", []).append(node)
            node = nxt
            recorder.checkpoint(node, state)
        raise GraphError("max transitions exceeded")
