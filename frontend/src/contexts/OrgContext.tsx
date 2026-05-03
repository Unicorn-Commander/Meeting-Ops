import React, { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { useAuth } from './AuthContext';
import {
  appendOrgQuery,
  clearStoredOrgSlug,
  DEFAULT_ORG_SLUG,
  getStoredOrgSlug,
  setStoredOrgSlug,
  type OrganizationMembership,
} from '../utils/organization';

interface OrgContextType {
  organizations: OrganizationMembership[];
  activeOrganization: OrganizationMembership | null;
  isLoading: boolean;
  hasAccess: boolean;
  switchOrganization: (slug: string) => void;
  getOrgQueryUrl: (url: string) => string;
}

const OrgContext = createContext<OrgContextType | undefined>(undefined);

function resolveActiveOrganization(
  organizations: OrganizationMembership[],
): OrganizationMembership | null {
  if (organizations.length === 0) {
    return null;
  }

  const storedSlug = getStoredOrgSlug();
  if (storedSlug) {
    const storedMatch = organizations.find((org) => org.slug === storedSlug);
    if (storedMatch) {
      return storedMatch;
    }
  }

  if (organizations.length === 1) {
    return organizations[0];
  }

  const defaultOrg = organizations.find((org) => org.slug === DEFAULT_ORG_SLUG);
  return defaultOrg ?? organizations[0];
}

export function OrgProvider({ children }: { children: ReactNode }) {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const organizations = useMemo(
    () => user?.organizations ?? [],
    [user],
  );
  const [activeOrganization, setActiveOrganization] = useState<OrganizationMembership | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (authLoading) {
      setIsLoading(true);
      return;
    }

    if (!isAuthenticated) {
      setActiveOrganization(null);
      clearStoredOrgSlug();
      setIsLoading(false);
      return;
    }

    const nextOrg = resolveActiveOrganization(organizations);
    setActiveOrganization(nextOrg);
    if (nextOrg) {
      setStoredOrgSlug(nextOrg.slug);
    } else {
      clearStoredOrgSlug();
    }
    setIsLoading(false);
  }, [authLoading, isAuthenticated, organizations]);

  const switchOrganization = (slug: string) => {
    const nextOrg = organizations.find((organization) => organization.slug === slug);
    if (!nextOrg) {
      return;
    }

    setActiveOrganization(nextOrg);
    setStoredOrgSlug(nextOrg.slug);
  };

  const value = useMemo<OrgContextType>(() => ({
    organizations,
    activeOrganization,
    isLoading,
    hasAccess: !isAuthenticated || organizations.length > 0,
    switchOrganization,
    getOrgQueryUrl: (url: string) => appendOrgQuery(url, activeOrganization?.slug),
  }), [organizations, activeOrganization, isLoading, isAuthenticated]);

  return (
    <OrgContext.Provider value={value}>
      {children}
    </OrgContext.Provider>
  );
}

export function useOrg() {
  const context = useContext(OrgContext);
  if (!context) {
    throw new Error('useOrg must be used within an OrgProvider');
  }
  return context;
}
