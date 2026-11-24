'use client'

import React, { useRef } from 'react'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface EditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  label: string
  initialValue: string
  onSave: (value: string) => void
}

export function EditDialog({
  open,
  onOpenChange,
  title,
  label,
  initialValue,
  onSave
}: EditDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  const handleSave = () => {
    onSave(inputRef.current?.value ?? initialValue)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="edit-input">{label}</Label>
          <Input
            key={`${open}:${initialValue}`}
            ref={inputRef}
            id="edit-input"
            defaultValue={initialValue}
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSave}>
            Save Changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
