import { configureStore, createSlice, PayloadAction } from '@reduxjs/toolkit';

// Simple slice to demonstrate interactive documentation state
interface PlaygroundState {
  theme: 'light' | 'dark';
  tutorialStep: number;
  userInput: string;
}

const initialState: PlaygroundState = {
  theme: 'light',
  tutorialStep: 1,
  userInput: '',
};

const playgroundSlice = createSlice({
  name: 'playground',
  initialState,
  reducers: {
    setTheme(state, action: PayloadAction<'light' | 'dark'>) {
      state.theme = action.payload;
    },
    nextStep(state) {
      state.tutorialStep += 1;
    },
    setUserInput(state, action: PayloadAction<string>) {
      state.userInput = action.payload;
    },
  },
});

export const { setTheme, nextStep, setUserInput } = playgroundSlice.actions;

export const store = configureStore({
  reducer: {
    playground: playgroundSlice.reducer,
  },
});

// Infer the `RootState` and `AppDispatch` types from the store itself
export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
