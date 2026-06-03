import { Routes } from '@angular/router';

export const devRoutes: Routes = [
  {
    path: 'dev/error-generator',
    loadComponent: () =>
      import('./error-generator/error-generator.component').then(
        (m) => m.ErrorGeneratorComponent,
      ),
    title: 'Faro error generator — XF Internal Linker',
  },
];
