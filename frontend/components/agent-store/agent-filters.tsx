"use client";

import { ChevronDown, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Capability, Visibility } from "@/lib/agent-store/types";
import { CAPABILITY_COLORS, CAPABILITY_LABELS } from "@/lib/agent-store/types";

export type SortKey = "popular" | "recent" | "name";
export type ScopeOption = Visibility | "native";

interface AgentFiltersProps {
  searchQuery: string;
  onSearchChange: (value: string) => void;
  capabilityFilter: Capability[];
  onCapabilityFilterChange: (value: Capability[]) => void;
  scopeFilter: ScopeOption[];
  onScopeFilterChange: (value: ScopeOption[]) => void;
  sortKey: SortKey;
  onSortChange: (value: SortKey) => void;
}

const CAPABILITY_OPTIONS: Capability[] = ["chat", "run", "scheduled", "async"];

const SCOPE_OPTIONS: { value: ScopeOption; label: string }[] = [
  { value: "public", label: "Public · 전사 공개" },
  { value: "team", label: "Team · 팀 공개" },
  { value: "private", label: "Private · 나만" },
  { value: "native", label: "Native · 기본 제공" },
];

const SCOPE_SHORT_LABEL: Record<ScopeOption, string> = {
  public: "Public",
  team: "Team",
  private: "Private",
  native: "Native",
};

function toggleItem<T>(arr: T[], value: T): T[] {
  return arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value];
}

export function AgentFilters({
  searchQuery,
  onSearchChange,
  capabilityFilter,
  onCapabilityFilterChange,
  scopeFilter,
  onScopeFilterChange,
  sortKey,
  onSortChange,
}: AgentFiltersProps) {
  const capabilityLabel =
    capabilityFilter.length === 0
      ? "전체 기능"
      : capabilityFilter.length === 1
        ? CAPABILITY_LABELS[capabilityFilter[0]]
        : `기능 ${capabilityFilter.length}개`;

  const scopeLabel =
    scopeFilter.length === 0
      ? "전체 범위"
      : scopeFilter.length === 1
        ? SCOPE_SHORT_LABEL[scopeFilter[0]]
        : `범위 ${scopeFilter.length}개`;

  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="text"
          placeholder="에이전트 검색 (이름 · 설명 · 태그)"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-10"
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex h-9 w-[160px] items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className={capabilityFilter.length === 0 ? "text-muted-foreground" : ""}>
                {capabilityLabel}
              </span>
              <ChevronDown className="h-4 w-4 opacity-50" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-[200px]">
            {CAPABILITY_OPTIONS.map((cap) => (
              <DropdownMenuCheckboxItem
                key={cap}
                checked={capabilityFilter.includes(cap)}
                onCheckedChange={() =>
                  onCapabilityFilterChange(toggleItem(capabilityFilter, cap))
                }
                onSelect={(e) => e.preventDefault()}
              >
                <span className="flex items-center gap-2">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: CAPABILITY_COLORS[cap] }}
                  />
                  {CAPABILITY_LABELS[cap]}
                </span>
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex h-9 w-[160px] items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className={scopeFilter.length === 0 ? "text-muted-foreground" : ""}>
                {scopeLabel}
              </span>
              <ChevronDown className="h-4 w-4 opacity-50" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-[220px]">
            {SCOPE_OPTIONS.map((opt) => (
              <DropdownMenuCheckboxItem
                key={opt.value}
                checked={scopeFilter.includes(opt.value)}
                onCheckedChange={() =>
                  onScopeFilterChange(toggleItem(scopeFilter, opt.value))
                }
                onSelect={(e) => e.preventDefault()}
              >
                {opt.label}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <Select value={sortKey} onValueChange={(v) => onSortChange(v as SortKey)}>
          <SelectTrigger className="h-9 w-[140px]">
            <SelectValue placeholder="정렬" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="popular">인기순 (설치 수)</SelectItem>
            <SelectItem value="recent">최근 실행순</SelectItem>
            <SelectItem value="name">이름순</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
