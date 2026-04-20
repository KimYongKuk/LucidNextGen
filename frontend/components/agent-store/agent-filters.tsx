"use client";

import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Capability, Visibility } from "@/lib/agent-store/types";
import { CAPABILITY_COLORS, CAPABILITY_LABELS } from "@/lib/agent-store/types";
import { DEPARTMENTS } from "@/lib/agent-store/mock-data";

export type SortKey = "popular" | "recent" | "name";

interface AgentFiltersProps {
  searchQuery: string;
  onSearchChange: (value: string) => void;
  capabilityFilter: Capability | "all";
  onCapabilityFilterChange: (value: Capability | "all") => void;
  departmentFilter: string;
  onDepartmentFilterChange: (value: string) => void;
  visibilityFilter: Visibility | "all";
  onVisibilityFilterChange: (value: Visibility | "all") => void;
  sortKey: SortKey;
  onSortChange: (value: SortKey) => void;
}

const CAPABILITY_OPTIONS: Capability[] = ["chat", "run", "scheduled", "async"];

export function AgentFilters({
  searchQuery,
  onSearchChange,
  capabilityFilter,
  onCapabilityFilterChange,
  departmentFilter,
  onDepartmentFilterChange,
  visibilityFilter,
  onVisibilityFilterChange,
  sortKey,
  onSortChange,
}: AgentFiltersProps) {
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
        <Select
          value={capabilityFilter}
          onValueChange={(v) => onCapabilityFilterChange(v as Capability | "all")}
        >
          <SelectTrigger className="h-9 w-[140px]">
            <SelectValue placeholder="기능" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체 기능</SelectItem>
            {CAPABILITY_OPTIONS.map((cap) => (
              <SelectItem key={cap} value={cap}>
                <span className="flex items-center gap-2">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: CAPABILITY_COLORS[cap] }}
                  />
                  {CAPABILITY_LABELS[cap]}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={departmentFilter} onValueChange={onDepartmentFilterChange}>
          <SelectTrigger className="h-9 w-[140px]">
            <SelectValue placeholder="부서" />
          </SelectTrigger>
          <SelectContent>
            {DEPARTMENTS.map((dept) => (
              <SelectItem key={dept} value={dept}>
                {dept}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={visibilityFilter}
          onValueChange={(v) => onVisibilityFilterChange(v as Visibility | "all")}
        >
          <SelectTrigger className="h-9 w-[140px]">
            <SelectValue placeholder="공개 범위" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체 범위</SelectItem>
            <SelectItem value="public">Public · 전사 공개</SelectItem>
            <SelectItem value="team">Team · 팀 공개</SelectItem>
            <SelectItem value="private">Private · 나만</SelectItem>
          </SelectContent>
        </Select>

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
