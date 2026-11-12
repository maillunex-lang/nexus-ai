import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

type Status = {service:string;version:string;database:string;mcp:string;security:string};
type User = {id:string;username:string;roles:string[]};
function App(){
 const [status,setStatus]=useState<Status|null>(null);
 const [user,setUser]=useState<User|null>(null);
 const [username,setUsername]=useState('');
 const [password,setPassword]=useState('');
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const refreshUser=async()=>{const r=await fetch('/api/auth/me',{credentials:'same-origin'});if(r.ok)setUser(await r.json());else setUser(null)};
 useEffect(()=>{fetch('/api/status').then(r=>r.json()).then(setStatus).catch(()=>setError('Сервер недоступен'));refreshUser().catch(()=>setUser(null))},[]);
 const signIn=async(e:React.FormEvent)=>{e.preventDefault();setBusy(true);setError('');try{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({username,password})});if(!r.ok){setError(r.status===429?'Слишком много попыток. Повторите через 15 минут.':'Не удалось войти. Проверьте учётные данные.');return}setPassword('');await refreshUser()}catch{setError('Не удалось подключиться к серверу')}finally{setBusy(false)}};
 const signOut=async()=>{setError('');try{const r=await fetch('/api/auth/logout',{method:'POST',credentials:'same-origin'});if(!r.ok)throw Error();setUser(null)}catch{setError('Ошибка выхода')}};
 return <main><header><span className="mark">✦</span><div><h1>NEXUS AI</h1><p>Secure Foundation · 0.1.3</p></div></header><section className="hero"><span className="eyebrow">ЦЕНТР УПРАВЛЕНИЯ</span><h2>Контрольная панель NEXUS AI</h2><p>Доступ к проектам и инструментам будет открываться только после проверки прав. OAuth для ChatGPT ещё в разработке.</p></section>
 <div className="grid"><article><small>Backend</small><strong>{status?.service ?? 'Ожидание'}</strong></article><article><small>PostgreSQL</small><strong>{status?.database ?? 'Нет данных'}</strong></article><article><small>MCP</small><strong>{status?.mcp ?? 'Нет данных'}</strong></article><article><small>Режим</small><strong>Безопасная диагностика</strong></article></div>
 <section className="auth"><h2>{user?'Учётная запись':'Вход оператора'}</h2>{user?<><p>Вы вошли как <strong>{user.username}</strong></p><p>Роли: {user.roles.join(', ')||'не назначены'}</p><button onClick={signOut}>Выйти</button></>:<form onSubmit={signIn}><label>Логин<input value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username" required minLength={3}/></label><label>Пароль<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" required/></label><button type="submit" disabled={busy}>{busy?'Проверка…':'Войти'}</button></form>}<p className="hint">Для входа необходим HTTPS. Первого владельца создают через защищённую консоль VPS, саморегистрация отключена.</p></section>
 {error&&<p role="alert" className="error">{error}</p>}<footer>Тестовый контур. Не открывать в интернет до завершения OAuth и аудита безопасности.</footer></main>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
