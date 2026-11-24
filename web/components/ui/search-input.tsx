'use client'

import * as React from "react"
import { Search, X } from "lucide-react"
import { Input } from "./input"
import { cn } from "@/lib/utils"

interface SearchInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  onSearch: (value: string) => void
  debounceMs?: number
  containerClassName?: string
}

export function SearchInput({ 
  containerClassName,
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
    <div className={cn("relative flex items-center", containerClassName)}>
      <Search aria-hidden="true" className="pointer-events-none absolute left-3 h-4 w-4 text-muted-foreground" />
      <Input
        {...props}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className={cn("pl-9 pr-9", className)}
      />
      {value && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={handleClear}
          className="absolute right-1.5 flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
