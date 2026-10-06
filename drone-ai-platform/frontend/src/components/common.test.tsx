import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatusBadge } from './common';

describe('StatusBadge', () => {
  it('renders status text and tone marker', () => {
    render(<StatusBadge tone="good" dot>PX4 online</StatusBadge>);
    expect(screen.getByText('PX4 online')).toBeInTheDocument();
    expect(screen.getByText('PX4 online')).toHaveClass('text-emerald-300');
  });
});
