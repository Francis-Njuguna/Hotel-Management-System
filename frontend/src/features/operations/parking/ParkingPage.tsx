import { useState } from 'react';
import { can, useSession } from '../../../services/session';
import { PageHeader, Switcher } from '../shared/ui';
import { AllocationDesk } from './AllocationDesk';
import { SpaceDesk } from './SpaceDesk';
import { VehicleDesk } from './VehicleDesk';

type Desk = 'allocations' | 'spaces' | 'vehicles';
export function ParkingPage() {
  const { user, loading } = useSession();
  const [desk, setDesk] = useState<Desk>('allocations');
  const manage = can(user, 'parking.manage');
  return <section className="page ops"><PageHeader title="Parking">Guest vehicles, numbered spaces and allocation history.</PageHeader>
    {loading ? <p role="status">Checking access…</p> : !can(user, 'parking.view') ?
      <p className="error" role="alert">Your account does not have access to parking.</p> : <>
        <Switcher label="Parking workspace" value={desk} change={setDesk} options={[
          { value: 'allocations', label: 'Allocations' }, { value: 'vehicles', label: 'Vehicles' }, { value: 'spaces', label: 'Spaces' },
        ]} />
        {desk === 'allocations' ? <AllocationDesk key={`a-${user?.id}`} manage={manage} /> : desk === 'vehicles' ?
          <VehicleDesk key={`v-${user?.id}`} register={manage && can(user, 'guests.view')} /> :
          <SpaceDesk key={`s-${user?.id}`} manage={manage} />}</>}
  </section>;
}
