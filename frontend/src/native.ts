/**
 * Small helpers so the same web code behaves well inside the Android app (Capacitor),
 * where browser-style downloads don't work.
 */
import { Capacitor } from '@capacitor/core'

export const isNative = () => Capacitor.isNativePlatform()

/** Save a file: normal download on the web, write + share sheet in the app. */
export async function saveFile(blob: Blob, filename: string) {
  if (!isNative()) {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    return
  }
  const [{ Filesystem, Directory, Encoding }, { Share }] = await Promise.all([
    import('@capacitor/filesystem'),
    import('@capacitor/share'),
  ])
  const text = await blob.text()
  const written = await Filesystem.writeFile({
    path: filename, data: text, directory: Directory.Cache, encoding: Encoding.UTF8,
  })
  await Share.share({ title: filename, url: written.uri, dialogTitle: 'Save or send the CSV' })
}
