async function httpGet(theUrl) {
    const response = await fetch(theUrl);
    const obj = await response.json();
    return {
        nombre: obj.nombre,
        identificacion: obj.identification_id,
        activity: obj.activity,
        email: obj.email,
    };
}
