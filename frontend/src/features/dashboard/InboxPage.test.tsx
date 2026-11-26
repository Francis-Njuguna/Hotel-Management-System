import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, send } from '../../services/api';
import { InboxPage } from './InboxPage';

vi.mock('../../services/api', async (original) => ({ ...await original<typeof import('../../services/api')>(), api: vi.fn(), send: vi.fn() }));
const get = vi.mocked(api);
const post = vi.mocked(send);
beforeEach(() => { get.mockReset(); post.mockReset(); });

it('preserves unread on failed write and displays read only after a successful command and fresh recipient list', async () => {
  const note = { id: 8, title: 'Fixture assignment', message: 'A synthetic notification.', read_at: null };
  const rows = { count: 1, next: null, previous: null, results: [note] };
  get.mockResolvedValueOnce(rows).mockResolvedValueOnce({ ...rows, results: [{ ...note, read_at: '2026-11-26T10:00:00Z' }] });
  post.mockRejectedValueOnce(new Error('fixture offline')).mockResolvedValueOnce({});
  render(<InboxPage />);
  const person = userEvent.setup();
  await person.click(await screen.findByRole('button', { name: 'Mark Fixture assignment as read' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('could not be confirmed');
  expect(screen.getByText('Unread')).toBeVisible();
  await person.click(screen.getByRole('button', { name: 'Mark Fixture assignment as read' }));
  expect(await screen.findByText('Read', { exact: true })).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('Notification marked as read');
  expect(post).toHaveBeenLastCalledWith('notifications/8/read/', 'POST', {});
  expect(get.mock.calls.map(([path]) => path)).toEqual(['notifications/?page=1&page_size=12', 'notifications/?page=1&page_size=12']);
});
