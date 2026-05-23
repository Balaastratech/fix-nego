/**
 * Test setup file for Vitest
 * 
 * This file is automatically loaded before running tests.
 * Configure global test utilities and mocks here.
 */

// Configure fast-check for property-based testing
// Minimum 100 iterations per property test as per design document
import fc from 'fast-check';
import '@testing-library/jest-dom/vitest';

// Set default number of runs for property tests
export const DEFAULT_NUM_RUNS = 100;

// Export configured fast-check instance
export { fc };
