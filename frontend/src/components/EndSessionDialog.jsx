import React, { useState } from "react"
import { Trash2, AlertTriangle, Loader2 } from "lucide-react"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { endSession, clearActiveSessionId, createSession } from "../api"

export default function EndSessionDialog({ trigger, onEnded, className = "" }) {
  const [open, setOpen] = useState(false)
  const [ending, setEnding] = useState(false)

  async function handleConfirmEnd() {
    setEnding(true)
    try {
      await endSession()
    } catch (err) {
      console.warn("Clean session termination encountered an issue:", err)
    } finally {
      clearActiveSessionId()
      try {
        await createSession()
      } catch (err) {
        console.warn("Failed to create new session after termination:", err)
      }
      setEnding(false)
      setOpen(false)
      if (onEnded) {
        onEnded()
      } else {
        window.location.href = "/"
      }
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger
        render={
          trigger || (
            <Button
              variant="outline"
              size="sm"
              className={`h-8 border-[#e0e0e0] bg-white text-[#7a7a7a] hover:text-[#dc2626] hover:border-[#dc2626]/40 hover:bg-red-50/50 text-xs font-normal gap-1.5 transition-colors ${className}`}
              title="End session and clear workspace data"
            >
              <Trash2 className="size-3.5" />
              <span className="hidden sm:inline">End Session</span>
            </Button>
          )
        }
      />
      <AlertDialogContent className="max-w-md bg-white border border-[#e0e0e0] shadow-xl p-5 rounded-2xl">
        <AlertDialogHeader className="space-y-2">
          <div className="flex items-center gap-3 text-red-600">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100/80">
              <AlertTriangle className="size-5 text-red-600" />
            </div>
            <AlertDialogTitle className="text-base font-semibold text-[#1d1d1f]">
              End Session & Clear Workspace?
            </AlertDialogTitle>
          </div>
          <AlertDialogDescription className="text-xs text-[#7a7a7a] leading-relaxed pt-1">
            This workspace uses temporary session storage. Ending the session will immediately
            and permanently remove all uploaded datasets, raster imagery, georeferencing
            ground control points, layer configurations, and pending exports.
            <br />
            <br />
            A new empty workspace session will be started. This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="mt-4 flex sm:flex-row justify-end gap-2 border-t border-[#f0f0f0] pt-4">
          <AlertDialogCancel
            disabled={ending}
            className="h-8 rounded-lg text-xs font-medium border-[#e0e0e0] text-[#1d1d1f] hover:bg-[#f5f5f7]"
          >
            Keep Session
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault()
              handleConfirmEnd()
            }}
            disabled={ending}
            className="h-8 rounded-lg text-xs font-medium bg-[#dc2626] hover:bg-[#b91c1c] text-white flex items-center gap-1.5"
          >
            {ending ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                <span>Clearing…</span>
              </>
            ) : (
              <span>End Session & Clear</span>
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
