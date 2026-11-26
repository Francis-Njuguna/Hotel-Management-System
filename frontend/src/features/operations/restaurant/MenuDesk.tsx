import { useState } from 'react';
import { useCollection, useWorkspace } from '../shared/data';
import { kes } from '../shared/format';
import { LoadState, Notice, Refresh, SearchBox, Status } from '../shared/ui';
import { MenuForm } from './MenuForm';
import { sameOriginImage, type MenuItem } from './model';

export function MenuDesk({ manage }: { manage: boolean }) {
  const [editing, setEditing] = useState<MenuItem | 'new' | null>(null);
  const [search, setSearch] = useState('');
  const [available, setAvailable] = useState('');
  const ws = useWorkspace();
  const list = useCollection<MenuItem>('menu-items/', { search, available }, ws.revision);

  return <section className="ops-stack" aria-label="Menu catalog"><div className="ops-section-head"><div><h2>Menu catalog</h2>
    <p className="muted">{manage ? 'Set prices and take unavailable items off sale without removing their history.' : 'Check item details, prices and availability.'}</p></div>
    {manage && editing === null && <button type="button" className="btn primary" onClick={() => { ws.clearNotice(); setEditing('new'); }}>New menu item</button>}</div>
    <Notice text={ws.notice} />
    {manage && editing !== null && <MenuForm key={editing === 'new' ? 'new' : editing.id} item={editing === 'new' ? undefined : editing}
      cancel={() => setEditing(null)} done={(message) => { setEditing(null); ws.changed(message); }} />}
    <div className="panel ops-stack"><div className="toolbar ops-filters"><SearchBox label="Search menu" value={search} change={setSearch} />
      <label className="field"><span>Item availability</span><select value={available} onChange={(e) => setAvailable(e.target.value)}>
        <option value="">All items</option><option value="true">Available</option><option value="false">Unavailable</option></select></label>
      <Refresh onClick={list.retry} /></div>
      <LoadState list={list} name="menu items" empty={search || available ? 'No menu items match these filters.' : 'No menu items have been added.'}>
        {(rows) => <div className="ops-menu-grid">{rows.map((item) => {
          const image = sameOriginImage(item.image);
          return <article key={item.id} className="ops-record" aria-label={item.name}><div className="ops-row-head"><div className="ops-title">
            {image && <img className="ops-thumb" src={image} alt="" loading="lazy" />}<div><div className="muted">{item.category}</div><h3>{item.name}</h3></div>
          </div><Status value={item.available ? 'available' : 'unavailable'} /></div>
            {item.description && <p>{item.description}</p>}<div className="ops-row-head"><strong>{kes(item.price)}</strong>
              {manage && !editing && <button type="button" className="btn secondary" aria-label={`Edit ${item.name}`}
                onClick={() => { ws.clearNotice(); setEditing(item); }}>Edit item</button>}</div></article>;
        })}</div>}</LoadState>
    </div>
  </section>;
}
