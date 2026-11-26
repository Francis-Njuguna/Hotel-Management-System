import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';
// findByRole waits for a rendered async result, not for a particular machine's
// scheduling speed while a PostgreSQL/Compose verification is also running.
configure({ asyncUtilTimeout: 5000 });
afterEach(cleanup);
