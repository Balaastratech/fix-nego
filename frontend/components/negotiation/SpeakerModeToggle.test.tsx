import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SpeakerModeToggle } from './SpeakerModeToggle';

describe('SpeakerModeToggle', () => {
  it('should render in auto mode', () => {
    render(
      <SpeakerModeToggle
        mode="auto"
        onModeChange={vi.fn()}
      />
    );
    expect(screen.getByText('Auto')).toBeInTheDocument();
  });

  it('should render in manual mode', () => {
    render(
      <SpeakerModeToggle
        mode="manual"
        onModeChange={vi.fn()}
      />
    );
    expect(screen.getByText('Manual')).toBeInTheDocument();
  });

  it('should call onModeChange with "manual" when toggled from auto', () => {
    const onModeChange = vi.fn();
    render(
      <SpeakerModeToggle
        mode="auto"
        onModeChange={onModeChange}
      />
    );
    fireEvent.click(screen.getByText('Auto'));
    expect(onModeChange).toHaveBeenCalledWith('manual');
  });

  it('should call onModeChange with "auto" when toggled from manual', () => {
    const onModeChange = vi.fn();
    render(
      <SpeakerModeToggle
        mode="manual"
        onModeChange={onModeChange}
      />
    );
    fireEvent.click(screen.getByText('Manual'));
    expect(onModeChange).toHaveBeenCalledWith('auto');
  });

  it('should not call onModeChange when disabled', () => {
    const onModeChange = vi.fn();
    render(
      <SpeakerModeToggle
        mode="auto"
        onModeChange={onModeChange}
        disabled={true}
      />
    );
    fireEvent.click(screen.getByText('Auto'));
    expect(onModeChange).not.toHaveBeenCalled();
  });

  it('should show mode indicator badge', () => {
    const { container } = render(
      <SpeakerModeToggle
        mode="auto"
        onModeChange={vi.fn()}
      />
    );
    const badge = container.querySelector('.animate-pulse');
    expect(badge).toBeInTheDocument();
  });

  it('should show tooltip on hover', async () => {
    render(
      <SpeakerModeToggle
        mode="auto"
        onModeChange={vi.fn()}
      />
    );
    const button = screen.getByText('Auto');
    fireEvent.mouseEnter(button);
    
    // Wait for tooltip to appear
    await screen.findByText('Auto Mode');
    expect(screen.getByText('Voice recognition identifies speakers automatically')).toBeInTheDocument();
  });

  it('should hide tooltip on mouse leave', () => {
    render(
      <SpeakerModeToggle
        mode="auto"
        onModeChange={vi.fn()}
      />
    );
    const button = screen.getByText('Auto');
    fireEvent.mouseEnter(button);
    fireEvent.mouseLeave(button);
    
    expect(screen.queryByText('Auto Mode')).not.toBeInTheDocument();
  });
});
