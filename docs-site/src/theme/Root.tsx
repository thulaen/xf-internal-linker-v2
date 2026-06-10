import React from 'react';
import { Provider } from 'react-redux';
import { store } from '../store';

// Default implementation, that you can customize
export default function Root({ children }: { children: React.ReactNode }) {
  return <Provider store={store}>{children}</Provider>;
}
