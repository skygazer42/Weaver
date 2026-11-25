export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadName(title: string, fallback: string) {
  return title.replace(/\.(?:html?|md|markdown|svg|png|pdf|docx)$/i, '')
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '-').trim().slice(0, 100) || fallback
}
