import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { HealthBadge } from '../components/HealthBadge';

describe('HealthBadge Component', () => {
  it('renders Healthy badge correctly', () => {
    render(<HealthBadge score={92} classification="Healthy" />);
    expect(screen.getByText('Healthy')).toBeInTheDocument();
    expect(screen.getByText('(92)')).toBeInTheDocument();
  });

  it('renders Critical badge correctly', () => {
    render(<HealthBadge score={18} classification="Critical" />);
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('(18)')).toBeInTheDocument();
  });

  it('derives classification from score when omitted', () => {
    render(<HealthBadge score={55} />);
    expect(screen.getByText('Needs Attention')).toBeInTheDocument();
    expect(screen.getByText('(55)')).toBeInTheDocument();
  });

  it('renders Not Assessed when score is null or undefined', () => {
    render(<HealthBadge score={null} />);
    expect(screen.getByText('Not Assessed')).toBeInTheDocument();
  });
});

