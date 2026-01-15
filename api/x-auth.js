// Vercel Serverless Function for X OAuth Token Exchange
// This exchanges the auth code for user info (bypasses CORS)

export default async function handler(req, res) {
    // Enable CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    const { code, code_verifier, redirect_uri } = req.body;

    if (!code || !code_verifier || !redirect_uri) {
        return res.status(400).json({ error: 'Missing required parameters' });
    }

    const CLIENT_ID = process.env.X_CLIENT_ID;
    const CLIENT_SECRET = process.env.X_CLIENT_SECRET;

    if (!CLIENT_ID || !CLIENT_SECRET) {
        return res.status(500).json({ error: 'Server misconfigured' });
    }

    try {
        // Step 1: Exchange code for access token
        const tokenResponse = await fetch('https://api.twitter.com/2/oauth2/token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': 'Basic ' + Buffer.from(`${CLIENT_ID}:${CLIENT_SECRET}`).toString('base64')
            },
            body: new URLSearchParams({
                grant_type: 'authorization_code',
                code: code,
                redirect_uri: redirect_uri,
                code_verifier: code_verifier
            })
        });

        const tokenData = await tokenResponse.json();

        if (!tokenResponse.ok) {
            console.error('Token exchange failed:', tokenData);
            return res.status(400).json({ error: 'Token exchange failed', details: tokenData });
        }

        // Step 2: Get user info
        const userResponse = await fetch('https://api.twitter.com/2/users/me', {
            headers: {
                'Authorization': `Bearer ${tokenData.access_token}`
            }
        });

        const userData = await userResponse.json();

        if (!userResponse.ok) {
            console.error('User fetch failed:', userData);
            return res.status(400).json({ error: 'Failed to get user info', details: userData });
        }

        // Return user info
        return res.status(200).json({
            id: userData.data.id,
            username: userData.data.username,
            name: userData.data.name
        });

    } catch (error) {
        console.error('Auth error:', error);
        return res.status(500).json({ error: 'Internal server error' });
    }
}
