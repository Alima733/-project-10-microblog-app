"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import axios from "axios";

interface Post {
  id: string;
  text: string;
  timestamp: string;
  owner_id: string;
  owner_username: string;
  likes_count: number;
  liked_by_me?: boolean;
}

const API_URL = "http://localhost:8000/api";

export default function UserProfilePage() {
  const params = useParams();
  const router = useRouter();
  const username = params?.username as string;
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchPosts = async () => {
    try {
      const token = localStorage.getItem("auth_token");
      const res = await axios.get(`${API_URL}/users/${username}/posts`, token ? { headers: { Authorization: `Bearer ${token}` } } : {});
      setPosts(res.data);
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        router.replace("/home");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!username) return;
    fetchPosts();
    // eslint-disable-next-line
  }, [username]);

  const handleLike = async (postId: string, liked: boolean) => {
    const token = localStorage.getItem("auth_token");
    if (!token) return;
    try {
      if (!liked) {
        await axios.post(`${API_URL}/posts/${postId}/like`, {}, { headers: { Authorization: `Bearer ${token}` } });
      } else {
        await axios.delete(`${API_URL}/posts/${postId}/like`, { headers: { Authorization: `Bearer ${token}` } });
      }
      fetchPosts();
    } catch (error) { }
  };

  if (loading) return <p>Загрузка...</p>;

  return (
    <div className="container mx-auto max-w-2xl p-4">
      <h1 className="text-2xl font-bold mb-6">Профиль: {username}</h1>
      {posts.length === 0 ? (
        <p>У пользователя пока нет постов.</p>
      ) : (
        <div className="space-y-4">
          {posts.map(post => (
            <div key={post.id} className="bg-white p-4 rounded-lg shadow relative">
              <p>{post.text}</p>
              <div className="text-xs text-gray-500 mt-2">
                <strong>{post.owner_username}</strong> - {new Date(post.timestamp).toLocaleString()}
              </div>
              <div className="flex items-center gap-2 mt-2">
                <button
                  onClick={() => handleLike(post.id, post.liked_by_me || false)}
                  className={`text-lg ${post.liked_by_me ? 'text-pink-500' : 'text-gray-400'} hover:text-pink-600`}
                  aria-label={post.liked_by_me ? 'Убрать лайк' : 'Поставить лайк'}
                >
                  ♥
                </button>
                <span className="text-sm">{post.likes_count}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
} 