# Staff workflow guide

This staff edition handles one anonymized property, Hotel A, in the Africa/Nairobi business day. The administration group provisions user accounts; a role grants only its department's actions. The department text by itself grants no access.

1. **Prepare the inventory.** A Super Administrator or Hotel Manager registers rooms with category, capacity, nightly KES rate, facilities and an optional photo. Register parking spaces and menu items. The Super Administrator creates named staff accounts and assigns their roles.
2. **At reception.** Search before registering a guest; guests sharing a name are not automatically merged. Search rooms for the intended dates, select named rooms, then create/confirm the reservation. The departure date is not a sold night. A conflict means another clerk or maintenance closure already claimed the room: reload availability and pick again.
3. **On arrival.** Check in an eligible confirmed booking. A vacant room can still be unready for admission: inspection, actual occupancy and blocking repairs are checked separately. The booking opens one folio with its agreed nightly rates.
4. **During the stay.** Restaurant staff can take a dine-in or room-service order. For room service select the open stay and its room. Serving posts the accepted menu prices once. Parking allocates an available space to a registered guest vehicle and keeps the release history.
5. **Settle and depart.** Review the invoice, including extra services. A cashier/accountant records **funds actually received**, the method and a stable reference, then can issue the receipt. Entering a mobile-money reference records a verified receipt; the application does not contact M-Pesa or initiate a transfer. An outstanding balance or live order prevents checkout. Checkout closes the folio and creates cleaning work.
6. **Turn the room.** Assign an active housekeeper, mark the work in progress, complete and inspect. Separately record/resolve maintenance. An inspection alone cannot sell a conflicting night or displace an occupant.
7. **Review.** The dashboard is calculated from operational records and the signed-in user's permissions. Scheduled arrivals/departures, financial charges posted today and money received today are different measures.

## Where to find booking, photos and staff roles

| Task | In the staff dashboard |
|---|---|
| Reserve for a guest | A **Receptionist**, **Hotel Manager** or **Super Administrator** opens **Reservations → New reservation**, selects the guest, enters dates and selects available rooms. Under **Booking mode**, choose **Confirm and reserve the rooms** to hold them. A pending booking does not hold them. A guest profile is not a login, and guests cannot book directly in this staff edition. |
| Add a room photo | **Rooms → Add room → Room photo**. Select the file and choose **Create room**. To change it later, open **Edit room** on the room card. |
| Add a menu photo | **Restaurant → Menu items → New menu item → Item image (optional)**. Select the file and choose **Create menu item**. Use **Edit item** to replace or remove it later. Both catalogs accept one optional still JPEG or PNG per record, up to 5 MiB and 12 megapixels. |
| Give a new staff member access | As **Super Administrator**, open **Staff & activity → Directory → Register staff**. Enter a unique username and staff email, select one **Role**, and enter the initial password twice. Choose **Review account → Create account**. The new staff member signs in with the username and password you set. To change someone’s role later, select **Edit → Role → Review changes → Confirm changes**; the staff member signs in again. |

## Application layout

`backend/config/` holds deployment settings and URL composition. `backend/apps/core/` owns identity/access, staff administration, protected media, audit and reporting. `lodging/` co-locates room inventory and occupancy-sensitive reservation commands; `housekeeping/`, `restaurant/`, `billing/` and `parking/` own their facts behind explicit service functions. `frontend/src/services/` is the cookie/CSRF API boundary. The React route shell and feature screens consume the same versioned API. See the [engineering contract](../system-design/build_contract.md) for field names and permissions.

The optional `seed_demo` command is deliberately separate from migrations. It labels its catalog as synthetic and creates no payment or payment-provider event. A fresh operational installation starts with no hotel figures.

**Recovery:** while signed in, use **Send verification email**, open the link in the staff mailbox and confirm it under the same account. An administrator changing the address clears its verified status. The reset form always gives the same public response. Local debug mail, when no SMTP relay is configured, stays in `.local/outbox/`; never publish or forward those files.
