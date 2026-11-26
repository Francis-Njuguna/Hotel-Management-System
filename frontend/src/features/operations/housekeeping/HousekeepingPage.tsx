import { useState } from 'react';
import { can, useSession } from '../../../services/session';
import { PageHeader, Switcher } from '../shared/ui';
import { CleaningQueue } from './CleaningQueue';
import { MaintenanceQueue } from './MaintenanceQueue';

type Desk = 'cleaning' | 'maintenance';
export function HousekeepingPage() {
  const { user, loading } = useSession();
  const [desk, setDesk] = useState<Desk>('cleaning');
  const cleaning = can(user, 'housekeeping.view');
  const maintenance = can(user, 'maintenance.view');
  const options: { value: Desk; label: string }[] = [];
  if (cleaning) options.push({ value: 'cleaning', label: 'Cleaning tasks' });
  if (maintenance) options.push({ value: 'maintenance', label: 'Maintenance' });
  const selected = options.some((o) => o.value === desk) ? desk : options[0]?.value;
  return <section className="page ops"><PageHeader title={!cleaning && maintenance ? 'Maintenance' : 'Housekeeping'}>
    {cleaning && maintenance ? 'Room cleaning, inspection and maintenance.' : maintenance ? 'Repair requests and room inventory blocks.' : 'Room cleaning tasks and inspections.'}</PageHeader>
    {loading ? <p role="status">Checking access…</p> : !user || !selected ?
      <p className="error" role="alert">Your account does not have access to housekeeping or maintenance.</p> : <>
        <Switcher label="Housekeeping workspace" value={selected} change={setDesk} options={options} />
        {selected === 'cleaning' ? <CleaningQueue key={`c-${user.id}-${can(user, 'housekeeping.manage')}`} manage={can(user, 'housekeeping.manage')}
          work={can(user, 'housekeeping.work')} lookupRooms={can(user, 'rooms.view')} userId={user.id} /> :
          <MaintenanceQueue key={`m-${user.id}-${can(user, 'maintenance.manage')}`} manage={can(user, 'maintenance.manage')} work={can(user, 'maintenance.work')}
            lookupRooms={can(user, 'rooms.view')} userId={user.id} />}</>}
  </section>;
}
