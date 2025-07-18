'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      router.replace('/home');
    } else {
      router.replace('/login');
    }
  }, [router]);

  return <p>Перенаправление...</p>;
}