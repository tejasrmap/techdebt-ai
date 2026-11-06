import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { Sidebar } from '../components/Sidebar';
import { Navbar } from '../components/Navbar';
import { AuthContext } from '../context/AuthContext';

const mockAuthValue = {
  user: {
    id: 'user-123',
    email: 'architect@example.com',
    full_name: 'Lead Architect',
    role: 'Administrator',
    org_id: 'org-123',
    organization_name: 'GT InnoX Enterprise'
  },
  token: 'mock-token',
  isAuthenticated: true,
  isLoading: false,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  refreshToken: vi.fn()
};

const renderWithAuth = (ui: React.ReactElement) => {
  return render(
    <AuthContext.Provider value={mockAuthValue as any}>
      {ui}
    </AuthContext.Provider>
  );
};

describe('Responsive and Accessibility Tests (WCAG 2.1 AA)', () => {
  it('renders sidebar with semantic navigation role and accessible label', () => {
    renderWithAuth(<Sidebar currentTab="overview" onSelectTab={vi.fn()} />);
    const nav = screen.getByRole('navigation', { name: /main navigation/i });
    expect(nav).toBeInTheDocument();
  });

  it('sets aria-current="page" strictly on the active tab item', () => {
    renderWithAuth(<Sidebar currentTab="projects" onSelectTab={vi.fn()} />);
    const activeBtn = screen.getByRole('button', { name: /projects/i });
    expect(activeBtn).toHaveAttribute('aria-current', 'page');

    const inactiveBtn = screen.getByRole('button', { name: /overview/i });
    expect(inactiveBtn).not.toHaveAttribute('aria-current');
  });

  it('invokes tab selection and mobile close handler on click', () => {
    const handleSelect = vi.fn();
    const handleClose = vi.fn();
    renderWithAuth(
      <Sidebar
        currentTab="overview"
        onSelectTab={handleSelect}
        isOpen={true}
        onClose={handleClose}
      />
    );

    const risksBtn = screen.getByRole('button', { name: /risk center/i });
    fireEvent.click(risksBtn);

    expect(handleSelect).toHaveBeenCalledWith('risks');
    expect(handleClose).toHaveBeenCalled();
  });

  it('renders navbar with accessible mobile menu toggle and ARIA expanded state', () => {
    const handleToggle = vi.fn();
    const { rerender } = renderWithAuth(
      <Navbar
        title="Executive Overview"
        onToggleSidebar={handleToggle}
        isSidebarOpen={false}
      />
    );

    const toggleBtn = screen.getByRole('button', { name: /toggle navigation menu/i });
    expect(toggleBtn).toBeInTheDocument();
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false');
    expect(toggleBtn).toHaveAttribute('aria-controls', 'sidebar-navigation');

    fireEvent.click(toggleBtn);
    expect(handleToggle).toHaveBeenCalled();

    rerender(
      <AuthContext.Provider value={mockAuthValue as any}>
        <Navbar
          title="Executive Overview"
          onToggleSidebar={handleToggle}
          isSidebarOpen={true}
        />
      </AuthContext.Provider>
    );

    const updatedToggleBtn = screen.getByRole('button', { name: /toggle navigation menu/i });
    expect(updatedToggleBtn).toHaveAttribute('aria-expanded', 'true');
  });

  it('provides accessible label on logout button', () => {
    renderWithAuth(<Sidebar currentTab="overview" onSelectTab={vi.fn()} />);
    const logoutBtn = screen.getByRole('button', { name: /log out of account/i });
    expect(logoutBtn).toBeInTheDocument();
  });
});
