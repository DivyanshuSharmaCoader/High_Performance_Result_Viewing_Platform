import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "./button";

export function OffsetPagination({
  offset,
  limit,
  total,
  onChange,
}: {
  offset: number;
  limit: number;
  total: number;
  onChange: (offset: number) => void;
}) {
  if (total === 0) return null;
  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <nav
      aria-label="Pagination"
      className="flex items-center justify-between gap-4 px-1 py-3 text-[13px] text-fg-subtle"
    >
      <p className="tabular">
        Showing <span className="font-medium text-fg">{from.toLocaleString()}</span>–
        <span className="font-medium text-fg">{to.toLocaleString()}</span> of{" "}
        <span className="font-medium text-fg">{total.toLocaleString()}</span>
      </p>
      <div className="flex gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          <ChevronLeft /> Previous
        </Button>
        <Button variant="secondary" size="sm" disabled={to >= total} onClick={() => onChange(offset + limit)}>
          Next <ChevronRight />
        </Button>
      </div>
    </nav>
  );
}

export function LoadMore({
  hasMore,
  loading,
  onLoadMore,
}: {
  hasMore: boolean;
  loading: boolean;
  onLoadMore: () => void;
}) {
  if (!hasMore) return null;
  return (
    <div className="flex justify-center py-4">
      <Button variant="secondary" size="sm" loading={loading} onClick={onLoadMore}>
        Load more
      </Button>
    </div>
  );
}
