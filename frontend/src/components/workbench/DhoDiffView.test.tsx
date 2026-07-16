import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DhoDiffView } from './DhoDiffView'

describe('DhoDiffView', () => {
  it('shows added, removed, and modified chapter changes', () => {
    render(<DhoDiffView diff={{
      chapters_added: [{ number: 31, title: '逃亡' }],
      chapters_removed: [{ number: 32, title: '旧盟约' }],
      chapters_modified: [{ number: 33, old: { title: '援救' }, new: { title: '背叛' } }],
    }} />)

    expect(screen.getByText('新增 1')).toBeInTheDocument()
    expect(screen.getByText(/第31章 逃亡/)).toBeInTheDocument()
    expect(screen.getByText(/\+ 背叛/)).toBeInTheDocument()
  })
})
