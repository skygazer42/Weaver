'use client'

import * as React from "react"
import { Search, X } from "lucide-react"
import { Input } from "./input"
import { cn } from "@/lib/utils"

interface SearchInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  onSearch: (value: string) => void
  debounceMs?: number
}

export function SearchInput({
  className,
  onSearch,
  debounceMs = 300,
  ...props
}: SearchInputProps) {
  const [value, setValue] = React.useState("")

  React.useEffect(() => {
    const timer = setTimeout(() => {
      onSearch(value)
    }, debounceMs)

    return () => clearTimeout(timer)
  }, [value, onSearch, debounceMs])

  const handleClear = () => {
    setValue("")
    onSearch("")
  }

  return (
    <div className={cn("relative flex items-center", className)}>
      <Search className="absolute left-3 h-4 w-4 text-muted-foreground" />
      <Input
        {...props}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className={cn("pl-10 pr-10")}
      />
      {value && (
        <button
          type="button"
          onClick={handleClear}
          aria-label="Clear search"
          title="Clear search"
          className="absolute right-3 rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
