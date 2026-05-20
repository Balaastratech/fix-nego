import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ENROLLMENT_SCRIPT, EnrollmentModal } from './EnrollmentModal';

describe('EnrollmentModal', () => {
  it('should not render when isOpen is false', () => {
    const { container } = render(
      <EnrollmentModal
        isOpen={false}
        onComplete={vi.fn()}
        onSkip={vi.fn()}
        onStartEnrollment={vi.fn()}
        enrollmentState="idle"
        countdown={null}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('should render when isOpen is true', () => {
    render(
      <EnrollmentModal
        isOpen={true}
        onComplete={vi.fn()}
        onSkip={vi.fn()}
        onStartEnrollment={vi.fn()}
        enrollmentState="idle"
        countdown={null}
      />
    );
    expect(screen.getByText('Voice Enrollment')).toBeInTheDocument();
  });

  it('should show live voice level during capturing state', () => {
    render(
      <EnrollmentModal
        isOpen={true}
        onComplete={vi.fn()}
        onSkip={vi.fn()}
        onStartEnrollment={vi.fn()}
        enrollmentState="capturing"
        countdown={3}
      />
    );
    expect(screen.getByText('Live voice level')).toBeInTheDocument();
    expect(screen.getByText('Listening for a stable voice sample...')).toBeInTheDocument();
  });

  it('should show success message when enrollment succeeds', () => {
    render(
      <EnrollmentModal
        isOpen={true}
        onComplete={vi.fn()}
        onSkip={vi.fn()}
        onStartEnrollment={vi.fn()}
        enrollmentState="success"
        countdown={null}
      />
    );
    expect(screen.getByText('Voice registered successfully!')).toBeInTheDocument();
    expect(screen.getByText('Continue')).toBeInTheDocument();
  });

  it('should show error message when enrollment fails', () => {
    const errorMessage = 'Audio too quiet. Please speak louder.';
    render(
      <EnrollmentModal
        isOpen={true}
        onComplete={vi.fn()}
        onSkip={vi.fn()}
        onStartEnrollment={vi.fn()}
        enrollmentState="error"
        countdown={null}
        errorMessage={errorMessage}
      />
    );
    expect(screen.getByText(errorMessage)).toBeInTheDocument();
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });

  it('should call onStartEnrollment when Start button is clicked', () => {
    const onStartEnrollment = vi.fn();
    render(
      <EnrollmentModal
        isOpen={true}
        onComplete={vi.fn()}
        onSkip={vi.fn()}
        onStartEnrollment={onStartEnrollment}
        enrollmentState="idle"
        countdown={null}
      />
    );
    fireEvent.click(screen.getByText('Start Enrollment'));
    expect(onStartEnrollment).toHaveBeenCalledTimes(1);
  });

  it('should show the enrollment script while capturing', () => {
    render(
      <EnrollmentModal
        isOpen={true}
        onComplete={vi.fn()}
        onSkip={vi.fn()}
        onStartEnrollment={vi.fn()}
        enrollmentState="capturing"
        countdown={20}
      />
    );
    expect(screen.getByText(new RegExp(ENROLLMENT_SCRIPT.slice(0, 40)))).toBeInTheDocument();
  });

  it('should call onSkip when Skip button is clicked', () => {
    const onSkip = vi.fn();
    render(
      <EnrollmentModal
        isOpen={true}
        onComplete={vi.fn()}
        onSkip={onSkip}
        onStartEnrollment={vi.fn()}
        enrollmentState="idle"
        countdown={null}
        allowSkip={true}
      />
    );
    fireEvent.click(screen.getByText('Skip'));
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it('should call onComplete when Continue button is clicked after success', () => {
    const onComplete = vi.fn();
    render(
      <EnrollmentModal
        isOpen={true}
        onComplete={onComplete}
        onSkip={vi.fn()}
        onStartEnrollment={vi.fn()}
        enrollmentState="success"
        countdown={null}
      />
    );
    fireEvent.click(screen.getByText('Continue'));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('should not show Skip button when allowSkip is false', () => {
    render(
      <EnrollmentModal
        isOpen={true}
        onComplete={vi.fn()}
        onSkip={vi.fn()}
        onStartEnrollment={vi.fn()}
        enrollmentState="idle"
        countdown={null}
        allowSkip={false}
      />
    );
    expect(screen.queryByText('Skip')).not.toBeInTheDocument();
  });

  it('should display volume meter with correct width during capturing', () => {
    const { container } = render(
      <EnrollmentModal
        isOpen={true}
        onComplete={vi.fn()}
        onSkip={vi.fn()}
        onStartEnrollment={vi.fn()}
        enrollmentState="capturing"
        countdown={5}
        audioLevel={75}
      />
    );
    const volumeMeter = container.querySelector('[style*="width: 75%"]');
    expect(volumeMeter).toBeInTheDocument();
  });
});
