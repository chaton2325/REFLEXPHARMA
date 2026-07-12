/**
 * Impression automatique des tickets de vente via l'agent d'impression local
 * ReflexPharma (voir dossier print_agent/), sans boite de dialogue navigateur.
 *
 * L'agent tourne sur le poste de caisse et ecoute sur http://127.0.0.1:38417.
 * Si l'agent n'est pas lance sur ce poste, isReady() renvoie false et
 * l'appelant doit se rabattre sur window.print().
 */
window.ReflexPrinter = (function () {
    const AGENT_BASE_URL = 'http://127.0.0.1:38417';
    const FETCH_TIMEOUT_MS = 1500;

    function withTimeout(promise, ms) {
        return Promise.race([
            promise,
            new Promise((_, reject) => setTimeout(() => reject(new Error('Delai depasse')), ms))
        ]);
    }

    function isSupported() {
        return true; // simple appel HTTP local, fonctionne dans tout navigateur
    }

    async function ping() {
        try {
            const res = await withTimeout(fetch(AGENT_BASE_URL + '/health', { method: 'GET' }), FETCH_TIMEOUT_MS);
            return res.ok;
        } catch (err) {
            return false;
        }
    }

    async function isReady() {
        return await ping();
    }

    async function listPrinters() {
        const res = await withTimeout(fetch(AGENT_BASE_URL + '/printers', { method: 'GET' }), FETCH_TIMEOUT_MS);
        if (!res.ok) throw new Error("Agent d'impression injoignable.");
        return res.json(); // { printers: [...], default: "...", selected: "..." }
    }

    async function setSelectedPrinter(name) {
        const res = await withTimeout(fetch(AGENT_BASE_URL + '/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ printer: name })
        }), FETCH_TIMEOUT_MS);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.message || "Impossible d'enregistrer l'imprimante.");
        return data;
    }

    async function printReceipt(receipt) {
        const res = await withTimeout(fetch(AGENT_BASE_URL + '/print', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(receipt)
        }), 8000);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.message || "Echec de l'impression.");
        return data;
    }

    async function printTestPage() {
        return printReceipt({
            pharmacyName: 'TEST AGENT',
            numero: 'TEST-0001',
            date: new Date().toLocaleDateString('fr-FR'),
            heure: new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
            vendeur: 'Test',
            client: 'Test',
            lignes: [{ nom: 'Article de test', qte: '1', pu: '0.00', total: '0.00' }],
            totalTtc: '0.00',
            modePaiement: 'test',
            montantRecu: '0.00',
            monnaieRendue: '0.00',
            watermark: 'TICKET DE TEST'
        });
    }

    return {
        isSupported: isSupported,
        isReady: isReady,
        ping: ping,
        listPrinters: listPrinters,
        setSelectedPrinter: setSelectedPrinter,
        printReceipt: printReceipt,
        printTestPage: printTestPage
    };
})();
