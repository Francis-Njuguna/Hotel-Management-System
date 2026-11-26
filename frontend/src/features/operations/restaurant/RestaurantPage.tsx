import { useState } from 'react';
import { can, useSession } from '../../../services/session';
import { PageHeader, Switcher } from '../shared/ui';
import { MenuDesk } from './MenuDesk';
import { OrderDesk } from './OrderDesk';

type Desk = 'orders' | 'menu';
export function RestaurantPage() {
  const { user, loading } = useSession();
  const [desk, setDesk] = useState<Desk>('orders');
  const manage = can(user, 'restaurant.manage');
  const work = can(user, 'restaurant.work');
  return <section className="page ops"><PageHeader title="Restaurant">Kitchen tickets, room service and the current menu.</PageHeader>
    {loading ? <p role="status">Checking access…</p> : !can(user, 'restaurant.view') ?
      <p role="alert" className="error">Your account does not have access to the restaurant.</p> : <>
        <Switcher label="Restaurant workspace" value={desk} change={setDesk}
          options={[{ value: 'orders', label: 'Orders' }, { value: 'menu', label: 'Menu items' }]} />
        {desk === 'menu' ? <MenuDesk key={`menu-${user?.id}-${manage}`} manage={manage} /> :
          <OrderDesk key={`orders-${user?.id}-${work}`} work={work} />}
      </>}
  </section>;
}
