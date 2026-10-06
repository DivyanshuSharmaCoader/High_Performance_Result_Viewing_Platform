import { api } from "@scorecode/api-client";
import { Badge, Button, ConfirmDialog, Menu, MenuContent, MenuItem, MenuTrigger, toast } from "@scorecode/ui";
import { useMutation } from "@tanstack/react-query";
import { Archive, ArchiveRestore, MoreHorizontal, Pencil } from "lucide-react";
import { useState } from "react";

import { toastError } from "../../lib/forms";
import { academicsApi, useInvalidateAcademics } from "./api";

export interface Archivable {
  id: string;
  code: string;
  name: string;
  archived_at: string | null;
}

/** Row actions shared by every academic resource: edit + archive/restore with confirmation. */
export function RowActions<T extends Archivable>({
  item,
  resource,
  noun,
  onEdit,
  archiveHint,
}: {
  item: T;
  resource: "departments" | "programs" | "cohorts" | "courses";
  noun: string;
  onEdit: (item: T) => void;
  archiveHint: string;
}) {
  const [confirm, setConfirm] = useState(false);
  const invalidate = useInvalidateAcademics();
  const archived = item.archived_at !== null;
  const toggle = useMutation({
    mutationFn: () =>
      api.put(`${academicsApi.base}/${resource}/${item.id}/archived`, { archived: !archived }),
    onSuccess: () => {
      invalidate();
      toast.success(archived ? `${item.code} restored` : `${item.code} archived`);
      setConfirm(false);
    },
    onError: (e) => {
      toastError(e);
      setConfirm(false);
    },
  });
  return (
    <>
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${item.code}`}>
            <MoreHorizontal />
          </Button>
        </MenuTrigger>
        <MenuContent>
          <MenuItem icon={<Pencil />} onSelect={() => onEdit(item)}>
            Edit {noun}
          </MenuItem>
          {archived ? (
            <MenuItem icon={<ArchiveRestore />} onSelect={() => setConfirm(true)}>
              Restore
            </MenuItem>
          ) : (
            <MenuItem icon={<Archive />} destructive onSelect={() => setConfirm(true)}>
              Archive
            </MenuItem>
          )}
        </MenuContent>
      </Menu>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`${archived ? "Restore" : "Archive"} ${item.code} — ${item.name}?`}
        description={archived ? `The ${noun} will appear in lists and pickers again.` : archiveHint}
        confirmLabel={archived ? "Restore" : "Archive"}
        variant={archived ? "primary" : "danger"}
        loading={toggle.isPending}
        onConfirm={() => toggle.mutate()}
      />
    </>
  );
}

export function NameCell({ code, name, archived }: { code: string; name: string; archived: boolean }) {
  return (
    <div className="min-w-0">
      <p className="truncate font-medium text-fg">
        {name}
        {archived && (
          <Badge className="ml-2" tone="neutral">
            Archived
          </Badge>
        )}
      </p>
      <p className="truncate font-mono text-xs text-fg-subtle">{code}</p>
    </div>
  );
}
