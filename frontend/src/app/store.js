import { configureStore } from '@reduxjs/toolkit';
import { setupListeners } from '@reduxjs/toolkit/query';
import { spendwiseApi } from '../shared/api/api';

export const store = configureStore({
  reducer: { [spendwiseApi.reducerPath]: spendwiseApi.reducer },
  middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(spendwiseApi.middleware),
});

setupListeners(store.dispatch);