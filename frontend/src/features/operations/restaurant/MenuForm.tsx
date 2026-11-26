import { useId, useState, type FormEvent } from 'react';
import { send } from '../../../services/api';
import { useMutation } from '../shared/data';
import { FormActions, FormHeading, Problem } from '../shared/ui';
import { sameOriginImage, type MenuItem } from './model';

export function MenuForm({ item, done, cancel }: { item?: MenuItem; done: (s: string) => void; cancel: () => void }) {
  const [name, setName] = useState(item?.name ?? '');
  const [category, setCategory] = useState(item?.category ?? '');
  const [price, setPrice] = useState(item?.price ?? '');
  const [description, setDescription] = useState(item?.description ?? '');
  const [available, setAvailable] = useState(item?.available ?? true);
  const [image, setImage] = useState<File | null>(null);
  const [removeImage, setRemoveImage] = useState(false);
  const hint = useId();
  const mutation = useMutation();
  const currentImage = sameOriginImage(item?.image);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !category.trim()) return mutation.fail('Provide both an item name and a category.');
    if (!/^\d{1,10}(?:\.\d{1,2})?$/.test(price)) {
      return mutation.fail('Enter a non-negative KES price with no more than two decimal places.');
    }
    if (image && image.size > 5 * 1024 * 1024) return mutation.fail('Choose an image no larger than 5 MB.');
    // Send only edits: a price/description edit must not re-enable an item another worker withdrew.
    const fields: Record<string, string | boolean | null> = {};
    if (!item || item.name !== name.trim()) fields.name = name.trim();
    if (!item || item.category !== category.trim()) fields.category = category.trim();
    if (!item || item.price !== price) fields.price = price;
    if (!item || item.description !== description.trim()) fields.description = description.trim();
    if (!item || item.available !== available) fields.available = available;
    if (removeImage && item?.image) fields.image = null;
    if (!image && !Object.keys(fields).length) return done('No menu changes to save.');
    let body: FormData | typeof fields = fields;
    if (image) {
      const form = new FormData();
      for (const [key, value] of Object.entries(fields)) form.set(key, String(value));
      form.set('image', image); body = form;
    }
    void mutation.run(() => send<MenuItem>(item ? `menu-items/${item.id}/` : 'menu-items/', item ? 'PATCH' : 'POST', body),
      (saved) => done(`${saved.name} ${item ? 'updated' : 'added to the menu'}.`));
  };

  return <form onSubmit={submit} className="panel ops-form" aria-label={item ? 'Edit menu item' : 'New menu item'} aria-busy={mutation.busy}>
    <FormHeading hint="Changes affect the menu for new orders, not prices already recorded on a ticket.">
      {item ? `Edit ${item.name}` : 'New menu item'}</FormHeading>
    <div className="form-grid"><label className="field"><span>Item name</span><input required maxLength={160} value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label className="field"><span>Category</span><input required maxLength={80} value={category} onChange={(e) => setCategory(e.target.value)} /></label>
      <label className="field"><span>Unit price (KES)</span><input required type="number" min="0" step="0.01" inputMode="decimal"
        value={price} onChange={(e) => setPrice(e.target.value)} /></label></div>
    <label className="field"><span>Description (optional)</span><textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
    {currentImage && <img src={currentImage} alt={`Current photo of ${item?.name}`} className="ops-thumb" />}
    {item?.image && <label className="ops-check"><input type="checkbox" checked={removeImage} disabled={!!image}
      onChange={(e) => setRemoveImage(e.target.checked)} />Remove current photo</label>}
    <label className="field"><span>{item?.image ? 'Replace image (optional)' : 'Item image (optional)'}</span>
      <input type="file" accept="image/jpeg,image/png" aria-describedby={hint} disabled={removeImage} onChange={(e) => setImage(e.target.files?.[0] ?? null)} /></label>
    <small id={hint} className="muted">Use a still JPEG or PNG, up to 5 MB and 12 megapixels. {item?.image ? 'The current photo stays unless removed or replaced.' : 'No photo is required to sell an item.'}</small>
    <label className="ops-check"><input type="checkbox" checked={available} onChange={(e) => setAvailable(e.target.checked)} />Available to order</label>
    <Problem text={mutation.error} focus /><FormActions busy={mutation.busy} submit={item ? 'Save menu changes' : 'Create menu item'} cancel={cancel} />
  </form>;
}
