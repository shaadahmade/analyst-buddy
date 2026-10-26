import { useEffect, useRef } from 'react'

export default function Sheet({ title, onClose, children }) {
  const ref = useRef(null)
  useEffect(() => { ref.current?.showModal() }, [])
  return (
    <dialog ref={ref} className="sheet" aria-label={title} onClose={onClose} onClick={(e) => e.target === ref.current && ref.current.close()}>
      <div className="sheet-body">
        <header className="sheet-head">
          <h2>{title}</h2>
          <button type="button" className="btn btn-ghost" onClick={() => ref.current.close()}>Close</button>
        </header>
        {children}
      </div>
    </dialog>
  )
}
