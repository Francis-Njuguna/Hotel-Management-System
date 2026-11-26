import { nairobiTime, readAudit } from './model';
import { Pagination, ReadResult, SearchBox, useRead, type Listing } from './ui';

export function ActivityLog({ listing }: { listing: Listing }) {
  const request = useRead(`audit/?${listing.params}`, readAudit);
  return <section className="panel" aria-label="Activity log">
    <h2>Activity log</h2><p className="muted">Recorded actions, newest first. Times are shown in Nairobi time.</p>
    <SearchBox label="Search activity" hint="Action, entity or staff username" listing={listing} />
    <ReadResult request={request} label="activity log">{data => <>
      {data.results.length ? <div className="table-wrap"><table aria-label="Recorded activity">
        <thead><tr><th scope="col">Recorded</th><th scope="col">Actor</th><th scope="col">Action</th>
          <th scope="col">Record</th><th scope="col">Summary</th></tr></thead>
        <tbody>{data.results.map(event => <tr key={event.id}>
          <td><time dateTime={event.created_at}>{nairobiTime(event.created_at)}</time></td>
          <td>{event.actor === null ? 'No staff actor' : event.actor_name ? `${event.actor_name} (#${event.actor})` : `Staff #${event.actor}`}</td>
          <th scope="row">{event.verb}</th><td>{event.entity} #{event.object_id}</td><td>{event.summary}</td>
        </tr>)}</tbody>
      </table></div> : <p className="empty">{listing.search ? 'No activity matches this search.' : 'No recorded activity to display.'}</p>}
      <Pagination label="Events" data={data} page={listing.page} onPage={listing.setPage} />
    </>}</ReadResult>
  </section>;
}
