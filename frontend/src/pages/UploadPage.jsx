import React, { useRef, useState } from "react"

import { readableApiError, uploadDataset } from "../api"
import UploadBox, { ACCEPTED_FORMATS } from "../components/UploadBox"
import UploadStatus from "../components/UploadStatus"

export default function UploadPage() {
  const replacementInputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [state, setState] = useState("idle")
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  function selectFile(nextFile) {
    setFile(nextFile)
    setState("selected")
    setProgress(0)
    setResult(null)
    setError(null)
  }

  function removeFile() {
    setFile(null)
    setState("idle")
    setProgress(0)
  }

  async function upload() {
    if (!file) return
    setState("uploading")
    setProgress(0)
    try {
      const uploaded = await uploadDataset(file, (event) => {
        if (event.total) setProgress(Math.round((event.loaded / event.total) * 100))
      })
      setResult(uploaded)
      setFile(null)
      setState("success")
    } catch (requestError) {
      setError(readableApiError(requestError, "Unable to upload the file."))
      setState("error")
    }
  }

  return (
    <main className="min-h-[calc(100vh-44px)] bg-parchment px-5 pb-20 phone:px-8">
      <section className="mx-auto max-w-[1100px] pt-20 text-center phone:pt-24">
        <h1 className="text-[40px] font-semibold leading-[1.1] tracking-[-0.28px] text-ink small-desktop:text-[56px] small-desktop:leading-[1.07]">
          Upload your map
        </h1>
        <p className="mt-3 text-[17px] text-muted phone:text-[24px] phone:font-light phone:leading-[1.5]">
          Add a raster or geographic dataset
        </p>

        <div className="mt-14 text-left phone:mt-16">
          {state === "idle" ? (
            <UploadBox disabled={false} onSelect={selectFile} />
          ) : (
            <UploadStatus
              state={state}
              file={file}
              progress={progress}
              result={result}
              error={error}
              onRemove={removeFile}
              onReplace={() => replacementInputRef.current?.click()}
              onUpload={upload}
              onRetry={() => setState(file ? "selected" : "idle")}
            />
          )}
        </div>

        <input
          ref={replacementInputRef}
          type="file"
          accept={ACCEPTED_FORMATS}
          className="sr-only"
          onChange={(event) => {
            const [nextFile] = event.target.files
            if (nextFile) selectFile(nextFile)
          }}
        />

        <div className="mt-12 text-center text-muted">
          <p className="text-[17px]">Supported map formats</p>
          <p className="mt-1 text-[14px] tracking-[-0.224px]">
            JPG · PNG · TIFF · KML · KMZ · SHP · OSM · PBF
          </p>
        </div>
      </section>
    </main>
  )
}
