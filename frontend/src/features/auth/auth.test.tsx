import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { TEST_EMAIL, TEST_PASSWORD } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

describe('auth screens', () => {
  it('redirects anonymous visitors to the login screen', async () => {
    renderApp('/', { authenticated: false });
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  });

  it('signs in and lands on the trajectory home screen', async () => {
    const user = userEvent.setup();
    renderApp('/login', { authenticated: false });
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Improving')).toBeInTheDocument();
  });

  it('shows a friendly error for a wrong password', async () => {
    const user = userEvent.setup();
    renderApp('/login', { authenticated: false });
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), 'not-the-one');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      "That email or password didn't match",
    );
  });

  it('surfaces other login failures with the server detail', async () => {
    server.use(
      http.post('/auth/login', () =>
        HttpResponse.json({ detail: 'Account locked' }, { status: 423 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/login', { authenticated: false });
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Account locked');
  });

  it('registers a new account and lands home', async () => {
    const user = userEvent.setup();
    renderApp('/register', { authenticated: false });
    await user.type(screen.getByLabelText('Your name'), 'Pat Example');
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText('Improving')).toBeInTheDocument();
  });

  it('rejects a too-short password before calling the API', async () => {
    const user = userEvent.setup();
    renderApp('/register', { authenticated: false });
    const passwordField = screen.getByLabelText('Password');
    passwordField.removeAttribute('minlength'); // bypass native validation to test ours
    await user.type(screen.getByLabelText('Your name'), 'Pat Example');
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(passwordField, 'short');
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('at least 8 characters');
  });

  it('shows the register error detail from the server', async () => {
    server.use(
      http.post('/auth/register', () =>
        HttpResponse.json({ detail: 'Email already registered' }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/register', { authenticated: false });
    await user.type(screen.getByLabelText('Your name'), 'Pat Example');
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Email already registered');
  });

  it('clears the stored session when the post-login profile read fails', async () => {
    server.use(
      http.get('/auth/me', () =>
        HttpResponse.json({ detail: 'Profile unavailable' }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/login', { authenticated: false });
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Profile unavailable');
    // The failed sign-in must not leave a live refresh token behind (kiosk risk).
    expect(sessionStorage.getItem('neuropathy.refresh_token')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  });

  it('signs out from the avatar button', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await screen.findByText('Improving');
    await user.click(screen.getByRole('button', { name: /Sign out/ }));
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    });
    expect(sessionStorage.getItem('neuropathy.refresh_token')).toBeNull();
  });
});
