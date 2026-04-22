# Mobile UI Design

## Goal
Make the app comfortable to use on phones: hamburger navigation drawer, touch-friendly forms with staged photo upload, and a card layout for the admin disc list.

## Navigation

On screens below `md` (768px), the navbar shows only the brand title and a `☰` hamburger button. The existing nav links are hidden via `hidden md:flex`. Tapping the hamburger renders a full-height drawer from the right with a semi-transparent backdrop. The drawer contains all the same links (My Discs, Wishlist, Profile, admin links if `user.is_admin`, Logout). Tapping any link or the backdrop closes the drawer. Desktop navigation is unchanged.

The drawer is conditionally rendered (`drawerOpen` state) so ARIA roles and focus work correctly. The `☰` button is `md:hidden`. The `✕` close button is inside the drawer.

## Forms — touch targets

All form inputs in `AdminDiscFormPage` use `py-3` (48px tall) and `w-full` on mobile. Labels are small-caps. The layout uses Tailwind responsive classes so desktop appearance is unchanged (`md:` prefixed variants restore any side-by-side layout). This applies to: text inputs, date inputs, `AutocompleteInput`, `PhoneInput` segments, and checkboxes.

## Photo upload — create mode

`AdminDiscFormPage` currently shows `PhotoUpload` only in edit mode because uploading requires a disc ID. In create mode, users can select photos that are staged in local state (`File[]`). After the disc is created (getting back its ID), staged photos are uploaded sequentially using `useUploadDiscPhoto`. A thumbnail preview strip shows staged photos before submit. This gives mobile users a single-step flow.

## Photo upload — edit mode (PhotoUpload component)

`PhotoUpload` adds a mobile tap button alongside the existing drag-and-drop zone:
- On mobile (`md:hidden`): a "Add Photos" tap button calls `open()` from `useDropzone`. The drag zone is hidden (`hidden md:block`).
- On desktop: drag zone shown as before, button hidden.

The hidden `<input {...getInputProps()} />` is rendered outside both so it is shared by both the button and the drag zone's `open()` call.

## "Save and Add Another"

`AdminDiscFormPage` in create mode gets a second submit button "Save and Add Another" alongside "Create". It shares the same validation and submission logic, but after saving and uploading staged photos, it resets the form to `defaultForm` (today's date, `is_found: true`) and clears staged photos instead of navigating away. Useful for entering a batch of discs at a pickup event.

This button is not shown in edit mode.

## Admin disc list — mobile card layout

On screens below `md`, the disc table (`hidden md:block`) is replaced by a stacked card list (`md:hidden`). Each card shows:
- Photo thumbnail (or grey placeholder)
- Disc name + manufacturer
- Color
- Owner name and phone number (if set)
- Status badge (Holding / Final notice / Returned)
- Found toggle button
- Returned checkbox + label
- Edit link and Delete button

Filter controls stack vertically above the cards. Pagination is unchanged.
