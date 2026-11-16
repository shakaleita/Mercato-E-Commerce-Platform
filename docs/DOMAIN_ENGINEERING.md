# Mercato engineering improvements

- Database migration for order status and idempotency keys.
- Repeated checkout idempotency to prevent duplicate stock deductions.
- Atomic cancellation restores inventory exactly once.
- Protected owner authentication and setup token (see SECURE_SETUP.md).
- Local demonstrator, not a payment-integrated production marketplace.
