# Diagrams

All diagrams are written in **Mermaid** so they render directly on GitHub, diff cleanly in Git, and stay next to the docs they illustrate. To export images (e.g. for the SE report), use the Mermaid CLI:

```bash
npx -y @mermaid-js/mermaid-cli -i docs/diagrams/sequence-diagrams.md -o build/diagrams/sequence.svg
```

| Diagram | UML / notation | File |
|---|---|---|
| System context & containers | C4-style (context, container) | [component-diagram.md](component-diagram.md) |
| Component diagram (backend modules) | UML component | [component-diagram.md](component-diagram.md#3-backend-component-diagram-modules) |
| Deployment diagrams (dev, demo, small prod, growing prod) | UML deployment | [deployment-diagram.md](deployment-diagram.md) |
| Use-case diagram | UML use case (rendered as flowchart) | [use-case-diagram.md](use-case-diagram.md) |
| Class diagrams (domain model, services, grading strategy, import pipeline) | UML class | [class-diagrams.md](class-diagrams.md) |
| Sequence diagrams (8 key flows) | UML sequence | [sequence-diagrams.md](sequence-diagrams.md) |
| Collaboration / communication diagrams | UML communication (numbered messages) | [collaboration-diagrams.md](collaboration-diagrams.md) |
| Activity / flow diagrams | UML activity / flowchart | [activity-diagrams.md](activity-diagrams.md) |
| State machine diagrams (exam, paper, import, publication, verification, tenant, subscription) | UML state | [state-diagrams.md](state-diagrams.md) |
| Entity-relationship diagrams | Crow's foot ER | [er-diagram.md](er-diagram.md) |
| Data flow diagrams (Level 0 and Level 1) | DFD (Yourdon-style, rendered as flowchart) | [data-flow-diagrams.md](data-flow-diagrams.md) |

**Notation notes.** Mermaid has no native UML use-case or communication diagram type; those are drawn with flowcharts using UML conventions (actors outside a system boundary, ovals for use cases; numbered messages on links for communication diagrams). If your faculty requires strict UML notation, the same content can be redrawn in StarUML/draw.io from these sources.
