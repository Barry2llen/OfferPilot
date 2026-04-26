"use client";

import Link from "next/link";
import Card from "@/app/components/ui/card";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import type { ModelProviderResponse } from "@/app/lib/api/types";

interface ProviderCardProps {
  provider: ModelProviderResponse;
  onEdit: (provider: ModelProviderResponse) => void;
  onDelete: (provider: ModelProviderResponse) => void;
  deleting: boolean;
}

export default function ProviderCard({
  provider,
  onEdit,
  onDelete,
  deleting,
}: ProviderCardProps) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <h3 className="font-display text-base font-semibold text-text-primary truncate">
              {provider.name}
            </h3>
            <Badge
              variant={provider.has_api_key ? "success" : "warning"}
              size="sm"
            >
              {provider.has_api_key ? "已配置密钥" : "未配置密钥"}
            </Badge>
          </div>
          <p className="text-sm text-text-secondary mb-2">
            {provider.provider}
            {provider.base_url && (
              <span className="text-text-muted ml-2 font-mono text-xs truncate block">
                {provider.base_url}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="ghost" size="sm" onClick={() => onEdit(provider)}>
            编辑
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(provider)}
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
