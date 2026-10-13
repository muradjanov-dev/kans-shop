import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { it, expect, vi } from 'vitest';
import { App } from '@/App';
vi.mock('@/hooks/useTelegramAuth', () => ({ useTelegramAuth: () => 'ready' }));
it('offers the catalog when a saved customer URL no longer exists', () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/old-campaign']}><App /></MemoryRouter></QueryClientProvider>);
  expect(screen.getByRole('heading', { name: 'Sahifa topilmadi' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Katalogga qaytish' })).toHaveAttribute('href', '/');
});
