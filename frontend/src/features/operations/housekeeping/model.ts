export const cleaningStates = ['pending', 'assigned', 'in_progress', 'completed', 'inspected'] as const;
export type CleaningStatus = (typeof cleaningStates)[number];

interface RoomWork {
  id: number;
  room: number;
  room_number?: string;
  assignee: number | null;
  assignee_name?: string | null;
  created_at: string;
}
export interface CleaningTask extends RoomWork { status: CleaningStatus; notes: string }
export interface Maintenance extends RoomWork {
  description: string; start: string; end: string; blocking: boolean; status: 'open' | 'resolved';
}
export function roomOf(work: RoomWork): string {
  return work.room_number ? `Room ${work.room_number}` : `Room ID ${work.room}`;
}

export function nextCleaningWork(status: CleaningStatus): { target: CleaningStatus; label: string } | null {
  switch (status) {
    case 'assigned': return { target: 'in_progress', label: 'Start cleaning' };
    case 'in_progress': return { target: 'completed', label: 'Complete cleaning' };
    default: return null;
  }
}
