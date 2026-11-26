import { useId, useState } from 'react';
import { useCollection, type Filters } from './data';
import { Pager, Problem, SearchBox } from './ui';

interface Props<T> {
  label: string;
  path: string;
  value: T | null;
  onChange: (value: T | null) => void;
  describe: (row: T) => string;
  filters?: Filters;
  eligible?: (row: T) => boolean;
  revision?: number;
  optional?: boolean;
  noChoice?: string;
  empty: string;
  searchLabel?: string;
}

/** Fetch a single bounded page from the authorized lookup, with native selection and paging. */
export function RecordPicker<T extends { id: number }>({
  label, path, value, onChange, describe, filters, eligible, revision, optional = false,
  noChoice = 'Choose an option', empty, searchLabel,
}: Props<T>) {
  const id = useId();
  const [search, setSearch] = useState('');
  const list = useCollection<T>(path, { ...filters, search }, revision, 20);
  const rows = (list.data?.results ?? []).filter((row) => !eligible || eligible(row));
  const outsidePage = value && !rows.some((row) => row.id === value.id);
  return <div className="field ops-picker" aria-busy={list.loading}><label htmlFor={id}>{label}</label>
    <select id={id} value={value?.id ?? ''} required={!optional} aria-describedby={`${id}-info`}
      onChange={(e) => onChange(rows.find((row) => String(row.id) === e.target.value) ?? null)}>
      <option value="">{noChoice}</option>
      {outsidePage && <option value={value.id}>{describe(value)} (selected)</option>}
      {rows.map((row) => <option key={row.id} value={row.id}>{describe(row)}</option>)}
    </select>
    <div id={`${id}-info`} className="ops-picker-info">
      {list.loading && <span className="muted" role="status">Loading choices…</span>}
      {list.error && <><Problem text={list.error}/><button type="button" className="btn secondary"
        onClick={list.retry}>Retry choices for {label}</button></>}
      {list.data && !rows.length && <span className="muted" role="status">{empty}</span>}
    </div>
    <details className="ops-find"><summary>{search ? `Search applied: ${search}` : 'Find or refresh choices'}</summary>
      {searchLabel && <SearchBox label={searchLabel} value={search} change={setSearch} />}
      <button type="button" className="btn secondary" onClick={() => { onChange(null); list.retry(); }}>
        {value ? 'Clear selection and refresh choices' : 'Refresh choices'}</button></details>
    <Pager list={list} name={label.toLowerCase()} />
  </div>;
}
