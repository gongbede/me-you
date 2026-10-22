import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ImagePlus, Send, X } from 'lucide-react'
import { MAX_POST_IMAGES, uploadPostImage, validatePostImage, type PostImageLimits, type UploadedPostImage } from '../api/media'
import { isValidPostContent, MAX_POST_LENGTH } from './feedHelpers'

type DraftImage = {
  id: string
  file: File
  previewUrl: string
  altText: string
  progress: number | null
  error: string | null
  assetId: string | null
}

export function PostComposer({
  onPost,
  isPosting,
  error,
  imageLimits,
  imageLimitsError,
  uploadImage = uploadPostImage,
}: {
  onPost: (content: string, attachments: UploadedPostImage[]) => Promise<void>
  isPosting: boolean
  error: string | null
  imageLimits: PostImageLimits | null
  imageLimitsError: string | null
  uploadImage?: typeof uploadPostImage
}) {
  const [content, setContent] = useState('')
  const [images, setImages] = useState<DraftImage[]>([])
  const [selectionError, setSelectionError] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const previewUrls = useRef(new Set<string>())

  useEffect(() => () => {
    for (const url of previewUrls.current) URL.revokeObjectURL(url)
  }, [])

  function replaceImage(id: string, update: Partial<DraftImage>) {
    setImages((current) => current.map((image) => image.id === id ? { ...image, ...update } : image))
  }

  function addImages(files: FileList | null) {
    if (!files || !imageLimits) return
    const available = MAX_POST_IMAGES - images.length
    const selected = Array.from(files)
    const nextFiles = selected.slice(0, Math.max(0, available))
    setSelectionError(selected.length > available ? `A post can include up to ${MAX_POST_IMAGES} images.` : null)
    setImages((current) => [
      ...current,
      ...nextFiles.map((file) => {
        const previewUrl = URL.createObjectURL(file)
        previewUrls.current.add(previewUrl)
        return {
          id: crypto.randomUUID(),
          file,
          previewUrl,
          altText: '',
          progress: null,
          error: validatePostImage(file, imageLimits),
          assetId: null,
        }
      }),
    ])
  }

  function removeImage(id: string) {
    const image = images.find((candidate) => candidate.id === id)
    if (image) {
      URL.revokeObjectURL(image.previewUrl)
      previewUrls.current.delete(image.previewUrl)
    }
    setImages((current) => current.filter((image) => image.id !== id))
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!isValidPostContent(content) || images.some((image) => image.error)) return
    setIsUploading(true)
    try {
      const attachments: UploadedPostImage[] = []
      for (const image of images) {
        let assetId = image.assetId
        if (!assetId) {
          replaceImage(image.id, { progress: 0, error: null })
          try {
            const uploaded = await uploadImage(image.file, imageLimits!, (progress) => {
              replaceImage(image.id, { progress })
            })
            assetId = uploaded.media_asset_id
            replaceImage(image.id, { assetId, progress: 100 })
          } catch (uploadError) {
            replaceImage(image.id, {
              progress: null,
              error: uploadError instanceof Error ? uploadError.message : 'Image upload failed.',
            })
            return
          }
        }
        attachments.push({ media_asset_id: assetId, alt_text: image.altText.trim() })
      }
      await onPost(content.trim(), attachments)
      setContent('')
      for (const image of images) {
        URL.revokeObjectURL(image.previewUrl)
        previewUrls.current.delete(image.previewUrl)
      }
      setImages([])
      setSelectionError(null)
    } catch {
      return
    } finally {
      setIsUploading(false)
    }
  }

  const isBusy = isPosting || isUploading

  return (
    <form className="post-composer" onSubmit={(event) => void submit(event)}>
      <label htmlFor="post-content">Share something with your community</label>
      <textarea
        id="post-content"
        name="content"
        rows={3}
        value={content}
        onChange={(event) => setContent(event.currentTarget.value)}
        placeholder="What are you learning today?"
        aria-describedby="post-character-count"
      />
      <div className="post-composer__media-controls">
        <label className="button button--outline post-composer__attach" htmlFor="post-images">
          <ImagePlus size={16} aria-hidden="true" /> Add images
        </label>
        <input
          id="post-images"
          className="sr-only"
          type="file"
          accept={imageLimits?.content_types.join(',')}
          multiple
          disabled={!imageLimits || isBusy || images.length >= MAX_POST_IMAGES}
          onChange={(event) => {
            addImages(event.currentTarget.files)
            event.currentTarget.value = ''
          }}
        />
        {imageLimits ? (
          <span className="field-help">Up to {MAX_POST_IMAGES} images · {Math.ceil(imageLimits.max_bytes / 1_000_000)} MB each</span>
        ) : imageLimitsError ? (
          <span className="form-alert" role="alert">Image options unavailable: {imageLimitsError}</span>
        ) : (
          <span className="field-help" role="status">Loading image options…</span>
        )}
      </div>
      {images.length > 0 && (
        <div className={`post-composer__images post-composer__images--${images.length}`}>
          {images.map((image) => (
            <div className="post-composer__image" key={image.id}>
              <img src={image.previewUrl} alt={image.altText || image.file.name} />
              <button
                className="icon-button post-composer__remove"
                type="button"
                aria-label={`Remove ${image.file.name}`}
                title="Remove image"
                disabled={isBusy}
                onClick={() => removeImage(image.id)}
              >
                <X size={16} aria-hidden="true" />
              </button>
              <label className="field">
                <span>Alt text</span>
                <input
                  type="text"
                  maxLength={200}
                  value={image.altText}
                  disabled={isBusy}
                  aria-label={`Alt text for ${image.file.name}`}
                  onChange={(event) => replaceImage(image.id, { altText: event.currentTarget.value })}
                />
              </label>
              {image.error && <p className="form-alert" role="alert">{image.file.name}: {image.error}</p>}
              {image.progress !== null && isUploading && (
                <div className="post-composer__progress" role="status">
                  <span>{image.file.name} · {image.progress}%</span>
                  <progress aria-label={`Upload progress for ${image.file.name}`} max={100} value={image.progress} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {selectionError && <p className="form-alert" role="alert">{selectionError}</p>}
      <div className="post-composer__footer">
        <span id="post-character-count" aria-live="polite">{Array.from(content).length.toLocaleString()} / {MAX_POST_LENGTH.toLocaleString()} · {images.length}/{MAX_POST_IMAGES} images</span>
        <button className="button button--primary" type="submit" disabled={!isValidPostContent(content) || images.some((image) => image.error) || isBusy}>
          <Send size={16} aria-hidden="true" /> {isBusy ? 'Posting…' : 'Post'}
        </button>
      </div>
      {error && <p className="form-alert" role="alert">{error}</p>}
    </form>
  )
}