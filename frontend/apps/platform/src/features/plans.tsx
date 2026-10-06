import { api, type PlansCatalog } from "@scorecode/api-client";
import { Badge, PageHeader, Skeleton, TBody, THead, Table, TableContainer, Td, Th } from "@scorecode/ui";
import { useQuery } from "@tanstack/react-query";
import { Check, Minus } from "lucide-react";

function Cell({ kind, value }: { kind: string; value: unknown }) {
  if (kind === "boolean") {
    return value ? (
      <Check className="mx-auto size-4 text-success" aria-label="Included" />
    ) : (
      <Minus className="mx-auto size-4 text-fg-disabled" aria-label="Not included" />
    );
  }
  if (value === null || value === undefined) return <span className="text-fg-subtle">Unlimited</span>;
  if (Array.isArray(value)) return <span className="text-xs">{value.join(", ")}</span>;
  return (
    <span className="tabular">
      {typeof value === "number" ? value.toLocaleString("en-IN") : String(value)}
    </span>
  );
}

export default function PlansPage() {
  const q = useQuery({ queryKey: ["plans"], queryFn: () => api.get<PlansCatalog>("/api/v1/platform/plans") });
  return (
    <>
      <PageHeader
        title="Plans & features"
        description="The catalogue every institution's entitlements are resolved from. Code checks features, never plan names."
      />
      {q.isPending || !q.data ? (
        <Skeleton className="h-96 rounded-xl" />
      ) : (
        <TableContainer>
          <Table>
            <THead>
              <tr>
                <Th className="sticky left-0 bg-surface-2">Feature</Th>
                {q.data.plans.map((p) => (
                  <Th key={p.code} className="text-center">
                    <span className="block normal-case tracking-normal text-fg">{p.name}</span>
                    <span className="block font-normal normal-case tracking-normal">
                      {p.price_paise_yearly === null
                        ? "Custom"
                        : p.price_paise_yearly === 0
                          ? "Free"
                          : `₹${(p.price_paise_yearly / 100).toLocaleString("en-IN")}/yr`}
                    </span>
                    {!p.is_public && <Badge className="mt-1">Private</Badge>}
                  </Th>
                ))}
              </tr>
            </THead>
            <TBody>
              {q.data.features.map((f) => (
                <tr key={f.key}>
                  <Td className="sticky left-0 bg-surface">
                    <span className="block">{f.description}</span>
                    <span className="block font-mono text-xs text-fg-subtle">{f.key}</span>
                  </Td>
                  {q.data.plans.map((p) => (
                    <Td key={p.code} className="text-center">
                      <Cell kind={f.kind} value={p.values[f.key]} />
                    </Td>
                  ))}
                </tr>
              ))}
            </TBody>
          </Table>
        </TableContainer>
      )}
    </>
  );
}
