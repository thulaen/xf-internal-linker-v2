import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

/**
 * Stat-strip displayed at the top of the Settings page.
 *
 * Extracted from `SettingsComponent` (which still owns the data sources
 * and the save-all flow) so the parent file shrinks and a future split
 * has one less reason to re-read the giant template.
 */
@Component({
  selector: 'app-settings-overview',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="settings-overview" id="settings-overview">
      <div class="settings-overview__stats">
        <article class="overview-stat">
          <span class="overview-stat__label" i18n="@@settings.overview.liveFeaturesLabel">Live features on</span>
          <strong>{{ currentFeatureCount }}</strong>
          <p i18n="@@settings.overview.liveFeaturesDesc">Ranking features currently active.</p>
        </article>

        <article class="overview-stat">
          <span class="overview-stat__label" i18n="@@settings.overview.recommendedOffLabel">Recommended still off</span>
          <strong>{{ currentOffCount }}</strong>
          <p i18n="@@settings.overview.recommendedOffDesc">Features from recommended preset still disabled.</p>
        </article>

        <article class="overview-stat">
          <span class="overview-stat__label" i18n="@@settings.overview.siloGroupsLabel">Silo groups</span>
          <strong>{{ siloGroupCount }}</strong>
          <p i18n="@@settings.overview.siloGroupsDesc">Active content families.</p>
        </article>

        <article class="overview-stat">
          <span class="overview-stat__label" i18n="@@settings.overview.assignedScopesLabel">Assigned scopes</span>
          <strong>{{ assignedScopeCount }}/{{ totalScopeCount }}</strong>
          <p i18n="@@settings.overview.assignedScopesDesc">Scopes mapped to silos.</p>
        </article>
      </div>
    </section>
  `,
  styles: [
    `
      .settings-overview {
        padding: var(--spacing-card);
        margin-bottom: var(--space-md);
      }
      .settings-overview__stats {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: var(--space-md);
      }
      .overview-stat {
        background: var(--color-bg-white);
        border: var(--card-border);
        border-radius: var(--card-border-radius);
        padding: var(--space-md);
      }
      .overview-stat__label {
        display: block;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--color-text-muted);
        margin-bottom: var(--space-xs);
      }
      .overview-stat strong {
        display: block;
        font-size: 22px;
        font-weight: 600;
        color: var(--color-text-primary);
        margin-bottom: var(--space-xs);
      }
      .overview-stat p {
        font-size: 12px;
        color: var(--color-text-secondary);
        margin: 0;
      }
    `,
  ],
})
export class SettingsOverviewComponent {
  @Input({ required: true }) currentFeatureCount = 0;
  @Input({ required: true }) currentOffCount = 0;
  @Input({ required: true }) siloGroupCount = 0;
  @Input({ required: true }) assignedScopeCount = 0;
  @Input({ required: true }) totalScopeCount = 0;
}
