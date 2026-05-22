import { useMemo } from 'react';
import {
  DEFAULT_TIER_FEATURES,
  useAuth,
  type Tier,
  type TierFeatures,
} from '../contexts/AuthContext';

/**
 * Hook for tier-based feature gating in components.
 *
 * Mirrors the backend `TIER_FEATURES.free` capabilities as the default
 * while `/api/auth/me` is in flight, so disabled buttons don't briefly
 * render as enabled on the first paint after login.
 *
 * Usage:
 *   const { tier, features, hasFeature } = useTierFeatures();
 *   if (hasFeature('server_live')) {
 *     return <ServerLiveButton />;
 *   }
 *
 * `tier` is the user's effective tier as resolved by the backend
 * (is_superuser users come through as 'enterprise'). When the user
 * hasn't loaded yet, both `tier` and `features` fall back to the free
 * defaults so the UI stays conservative until we know better.
 */
export interface UseTierFeaturesReturn {
  tier: Tier;
  features: TierFeatures;
  hasFeature: (key: keyof TierFeatures) => boolean;
}

export function useTierFeatures(): UseTierFeaturesReturn {
  const { user } = useAuth();

  return useMemo<UseTierFeaturesReturn>(() => {
    const tier: Tier = user?.tier ?? 'free';
    const features: TierFeatures = user?.tier_features ?? DEFAULT_TIER_FEATURES;

    return {
      tier,
      features,
      hasFeature: (key: keyof TierFeatures) => Boolean(features[key]),
    };
  }, [user]);
}
