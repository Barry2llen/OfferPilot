"use client";

import Card from "@/app/components/ui/card";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import type { ModelSelectionResponse } from "@/app/lib/api/types";

interface SelectionCardProps {
  selection: ModelSelectionResponse;
  onEdit: (selection: ModelSelectionResponse) => void;
  onDelete: (selection: ModelSelectionResponse) => void;
  deleting: boolean;
}

export default function SelectionCard({
  selection,
  onEdit,
  onDelete,
  deleting,
}: SelectionCardProps) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <h3 className="font-display text-base font-semibold text-text-primary">
              {selection.model_name}
            </h3>
            <Badge variant="info" size="sm">
              ID: {selection.id}
            </Badge>
          </div>
          <p className="text-sm text-text-secondary">
            供应商: {selection.provider.name} ({selection.provider.provider})
          </p>
          <div className="flex items-center gap-2 mt-1.5">
            <Badge
              variant={selection.supports_image_input ? "success" : "neutral"}
              size="sm"
            >
              {selection.supports_image_input ? "支持图片" : "仅文本"}
            </Badge>
            {selection.provider.has_api_key ? null : (
              <Badge variant="warning" size="sm">
                供应商未配置密钥
              </Badge>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="ghost" size="sm" onClick={() => onEdit(selection)}>
            编辑
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(selection)}
            disabled={deleting}
            className="text-error-text hover:bg-error-bg"
          >
            {deleting ? "删除中..." : "删除"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
