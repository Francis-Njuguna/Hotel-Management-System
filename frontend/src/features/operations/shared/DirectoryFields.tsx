import { RecordPicker } from './RecordPicker';
import { personLabel, roomLabel, type RoomChoice, type StaffChoice } from './format';

export function RoomPicker({ value, change }: { value: RoomChoice | null; change: (room: RoomChoice | null) => void }) {
  return <RecordPicker label="Room" path="rooms/" value={value} onChange={change} describe={roomLabel}
    noChoice="Choose a room" empty="No rooms on this page match your search." searchLabel="Search rooms by number" />;
}

export function AssigneePicker({ role, value, change, required = false }: {
  role: 'Housekeeping Staff' | 'Maintenance Staff' | 'Restaurant Staff';
  value: StaffChoice | null; change: (staff: StaffChoice | null) => void; required?: boolean;
}) {
  return <RecordPicker label={required ? 'Assign to' : 'Assign to (optional)'} path="staff/assignees/"
    filters={{ role }} value={value} onChange={change} describe={personLabel} optional={!required}
    noChoice={required ? 'Choose an active staff member' : 'Leave unassigned'}
    empty={`No eligible ${role.toLowerCase()} on this page.`} searchLabel={`Search ${role.toLowerCase()} by name`} />;
}
